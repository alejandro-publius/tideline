/**
 * Imperative three.js controller for the Tideline globe.
 *
 * Kept out of React on purpose: the scene is built once and then *mutated* as
 * data and selection change, which is far cheaper (and less bug-prone) than
 * reconciling a WebGL scene graph through a virtual DOM. The React shell
 * (`Globe.tsx`) owns the lifecycle and forwards prop changes to the methods
 * returned by `createGlobeScene`.
 *
 * This module imports `three` and the 55 KB world-coastline TopoJSON, so it
 * only ever loads inside the lazily-imported globe chunk — never on first paint.
 */
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { mesh } from 'topojson-client'
import landTopo from 'world-atlas/land-110m.json'
import { latLngToVec3, pillarHeight, surgeColor } from '../lib/globe'

export interface GlobeStation {
  id: string
  name: string
  state: string
  lat: number
  lon: number
  /** observed − predicted, metres; null when the station has no fresh reading */
  surge: number | null
  /** true when the station is at or beyond its NWS minor flood stage */
  flooding: boolean
}

export interface GlobeHandlers {
  onSelect: (id: string) => void
  onHover: (station: GlobeStation | null, clientX: number, clientY: number) => void
}

export interface GlobeScene {
  setStations(stations: GlobeStation[]): void
  setSelected(id: string | null): void
  setReducedMotion(reduced: boolean): void
  setActive(active: boolean): void
  resize(): void
  dispose(): void
}

const GLOBE_RADIUS = 1
const CAMERA_DISTANCE = 2.75
const SPIN_SPEED = 0.045 // radians / second — a slow, stately turn
const OCEAN_COLOR = 0x0a1b30
const COASTLINE_COLOR = 0x5fd0e8
const ATMOSPHERE_COLOR = 0x3aa6d8
const GRATICULE_COLOR = 0x2b5a78
const MUTED_PILLAR = 0x6b7a86

/** One soft radial-gradient sprite texture, reused for every glow. */
function makeGlowTexture(): THREE.Texture {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255,255,255,1)')
  g.addColorStop(0.25, 'rgba(255,255,255,0.85)')
  g.addColorStop(0.5, 'rgba(255,255,255,0.35)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

/** Coastlines (and a faint graticule) as line geometry on the sphere. */
function buildCoastlines(radius: number): THREE.LineSegments {
  const land = mesh(landTopo, landTopo.objects.land)
  const positions: number[] = []
  for (const line of land.coordinates) {
    for (let i = 0; i < line.length - 1; i++) {
      const [lon1, lat1] = line[i]
      const [lon2, lat2] = line[i + 1]
      positions.push(...latLngToVec3(lat1, lon1, radius), ...latLngToVec3(lat2, lon2, radius))
    }
  }
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  const mat = new THREE.LineBasicMaterial({
    color: COASTLINE_COLOR,
    transparent: true,
    opacity: 0.62,
    depthWrite: false,
  })
  return new THREE.LineSegments(geom, mat)
}

function buildGraticule(radius: number): THREE.LineSegments {
  const positions: number[] = []
  const STEP = 2 // degrees between sampled points along a line
  // parallels every 30°
  for (let lat = -60; lat <= 60; lat += 30) {
    for (let lon = -180; lon < 180; lon += STEP) {
      positions.push(...latLngToVec3(lat, lon, radius), ...latLngToVec3(lat, lon + STEP, radius))
    }
  }
  // meridians every 30°
  for (let lon = -180; lon < 180; lon += 30) {
    for (let lat = -88; lat < 88; lat += STEP) {
      positions.push(...latLngToVec3(lat, lon, radius), ...latLngToVec3(lat + STEP, lon, radius))
    }
  }
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
  const mat = new THREE.LineBasicMaterial({
    color: GRATICULE_COLOR,
    transparent: true,
    opacity: 0.16,
    depthWrite: false,
  })
  return new THREE.LineSegments(geom, mat)
}

function buildAtmosphere(radius: number): THREE.Mesh {
  const geom = new THREE.SphereGeometry(radius * 1.19, 48, 48)
  const mat = new THREE.ShaderMaterial({
    uniforms: { glowColor: { value: new THREE.Color(ATMOSPHERE_COLOR) } },
    vertexShader: `
      varying vec3 vNormal;
      void main() {
        vNormal = normalize(normalMatrix * normal);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }`,
    fragmentShader: `
      varying vec3 vNormal;
      uniform vec3 glowColor;
      void main() {
        float intensity = pow(0.68 - dot(vNormal, vec3(0.0, 0.0, 1.0)), 3.0);
        gl_FragColor = vec4(glowColor, 1.0) * clamp(intensity, 0.0, 1.0);
      }`,
    side: THREE.BackSide,
    blending: THREE.AdditiveBlending,
    transparent: true,
    depthWrite: false,
  })
  return new THREE.Mesh(geom, mat)
}

function buildStars(): THREE.Points {
  const COUNT = 1400
  const positions = new Float32Array(COUNT * 3)
  const colors = new Float32Array(COUNT * 3)
  const tint = new THREE.Color()
  for (let i = 0; i < COUNT; i++) {
    // uniform-ish on a far shell; deterministic-free randomness is fine for stars
    const r = 30 + Math.random() * 40
    const theta = Math.random() * Math.PI * 2
    const phi = Math.acos(2 * Math.random() - 1)
    positions[i * 3] = r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = r * Math.cos(phi)
    tint.setHSL(0.55 + Math.random() * 0.1, 0.3, 0.7 + Math.random() * 0.3)
    colors[i * 3] = tint.r
    colors[i * 3 + 1] = tint.g
    colors[i * 3 + 2] = tint.b
  }
  const geom = new THREE.BufferGeometry()
  geom.setAttribute('position', new THREE.BufferAttribute(positions, 3))
  geom.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  const mat = new THREE.PointsMaterial({
    size: 0.18,
    sizeAttenuation: true,
    vertexColors: true,
    transparent: true,
    opacity: 0.9,
    depthWrite: false,
  })
  return new THREE.Points(geom, mat)
}

interface Pillar {
  station: GlobeStation
  dir: THREE.Vector3
  column: THREE.Mesh
  tip: THREE.Sprite
  ring: THREE.Mesh | null // flood-stage radar ping
  hit: THREE.Mesh // invisible raycast target at the tip
  baseTipScale: number
}

const UP = new THREE.Vector3(0, 1, 0)

export function createGlobeScene(
  container: HTMLElement,
  handlers: GlobeHandlers,
  opts: { reducedMotion: boolean },
): GlobeScene {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setSize(container.clientWidth, container.clientHeight || 1)
  renderer.setClearColor(0x000000, 0)
  container.appendChild(renderer.domElement)

  const scene = new THREE.Scene()
  const camera = new THREE.PerspectiveCamera(
    42,
    Math.max(container.clientWidth, 1) / Math.max(container.clientHeight, 1),
    0.1,
    200,
  )
  // Frame North America on load — every station is on a US coast.
  camera.position.fromArray(latLngToVec3(26, -95, CAMERA_DISTANCE))

  const controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.08
  controls.enablePan = false
  controls.rotateSpeed = 0.5
  controls.zoomSpeed = 0.6
  controls.minDistance = 1.55
  controls.maxDistance = 6
  controls.target.set(0, 0, 0)

  // Must run AFTER constructing OrbitControls — its connect() stamps
  // touch-action:'none' on the canvas, which would trap vertical page scroll
  // on a full-width hero. 'pan-y' lets the browser claim vertical swipes
  // (OrbitControls recovers via pointercancel) while horizontal drags orbit.
  renderer.domElement.style.touchAction = 'pan-y'

  // Wheel-zoom only with a modifier held: a hero at the top of the page must
  // never hijack normal page scrolling. Capture phase on the container so the
  // flag is set before OrbitControls' own wheel listener consults it; touch
  // pinch re-enables zoom on pointerdown below.
  controls.enableZoom = false
  const onWheelGate = (e: WheelEvent) => {
    controls.enableZoom = e.ctrlKey || e.metaKey
  }
  container.addEventListener('wheel', onWheelGate, { capture: true, passive: true })

  const glowTexture = makeGlowTexture()

  // Lighting: a soft key light gives the coastlines a living terminator as the
  // globe turns; low ambient keeps the night side legible rather than black.
  scene.add(new THREE.AmbientLight(0x8899bb, 0.7))
  const key = new THREE.DirectionalLight(0xffffff, 1.15)
  key.position.set(-2, 1.2, 2.5)
  scene.add(key)

  const stars = buildStars()
  scene.add(stars)
  scene.add(buildAtmosphere(GLOBE_RADIUS))

  // Everything that should turn with the planet lives under one group.
  const globeGroup = new THREE.Group()
  scene.add(globeGroup)

  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(GLOBE_RADIUS, 96, 96),
    new THREE.MeshStandardMaterial({
      color: OCEAN_COLOR,
      roughness: 0.92,
      metalness: 0.0,
      emissive: 0x030a16,
      emissiveIntensity: 0.55,
    }),
  )
  globeGroup.add(earth)
  globeGroup.add(buildGraticule(GLOBE_RADIUS * 1.001))
  globeGroup.add(buildCoastlines(GLOBE_RADIUS * 1.002))

  const pillarGroup = new THREE.Group()
  globeGroup.add(pillarGroup)

  let pillars: Pillar[] = []
  let selectedId: string | null = null
  // Caches kept in sync by buildPillars/applySelection so the render loop and
  // pointermove handler never allocate: the raycast target list (earth first,
  // so far-side stations are occluded) and the currently selected pillar.
  let pickTargets: THREE.Object3D[] = []
  let selectedPillar: Pillar | null = null
  let reducedMotion = opts.reducedMotion
  const color = new THREE.Color()

  function disposePillars() {
    for (const p of pillars) {
      p.column.geometry.dispose()
      ;(p.column.material as THREE.Material).dispose()
      ;(p.tip.material as THREE.Material).dispose()
      if (p.ring) {
        p.ring.geometry.dispose()
        ;(p.ring.material as THREE.Material).dispose()
      }
      p.hit.geometry.dispose()
      ;(p.hit.material as THREE.Material).dispose()
    }
    pillarGroup.clear()
    pillars = []
  }

  function buildPillars(stations: GlobeStation[]) {
    disposePillars()
    for (const station of stations) {
      const dir = new THREE.Vector3().fromArray(latLngToVec3(station.lat, station.lon, 1)).normalize()
      const height = pillarHeight(station.surge, GLOBE_RADIUS)
      const hex = station.surge == null ? MUTED_PILLAR : surgeColor(station.surge)
      color.set(hex)

      // Column: a thin cylinder standing radially off the surface.
      const column = new THREE.Mesh(
        new THREE.CylinderGeometry(0.004, 0.007, height, 8, 1, true),
        new THREE.MeshBasicMaterial({ color: color.clone(), transparent: true, opacity: 0.9 }),
      )
      column.quaternion.setFromUnitVectors(UP, dir)
      column.position.copy(dir).multiplyScalar(GLOBE_RADIUS + height / 2)
      pillarGroup.add(column)

      // Tip: an additive glow sprite — the luminous "reading".
      const baseTipScale = station.surge == null ? 0.05 : 0.07
      const tip = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: glowTexture,
          color: color.clone(),
          transparent: true,
          opacity: 0.95,
          blending: THREE.AdditiveBlending,
          depthWrite: false,
        }),
      )
      tip.scale.setScalar(baseTipScale)
      tip.position.copy(dir).multiplyScalar(GLOBE_RADIUS + height)
      pillarGroup.add(tip)

      // Flood-stage radar ping: an expanding ring flat against the surface.
      let ring: THREE.Mesh | null = null
      if (station.flooding) {
        ring = new THREE.Mesh(
          new THREE.RingGeometry(0.02, 0.03, 32),
          new THREE.MeshBasicMaterial({
            color: 0xff6a3d,
            transparent: true,
            opacity: 0.7,
            side: THREE.DoubleSide,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
          }),
        )
        ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), dir)
        ring.position.copy(dir).multiplyScalar(GLOBE_RADIUS + 0.003)
        pillarGroup.add(ring)
      }

      // Invisible, generously sized hit target for reliable picking.
      const hit = new THREE.Mesh(
        new THREE.SphereGeometry(0.05, 8, 8),
        new THREE.MeshBasicMaterial({ visible: false }),
      )
      hit.position.copy(tip.position)
      hit.userData.stationId = station.id
      pillarGroup.add(hit)

      pillars.push({ station, dir, column, tip, ring, hit, baseTipScale })
    }
    pickTargets = [earth, ...pillars.map((p) => p.hit)]
    applySelection()
  }

  // A soft white halo drawn behind the selected station's tip. Attached to
  // globeGroup (identity transform relative to pillarGroup) so it survives
  // pillarGroup.clear() when station data is rebuilt.
  const selectionHalo = new THREE.Sprite(
    new THREE.SpriteMaterial({
      map: glowTexture,
      color: 0xffffff,
      transparent: true,
      opacity: 0.0,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    }),
  )
  selectionHalo.scale.setScalar(0.001)
  selectionHalo.visible = false
  globeGroup.add(selectionHalo)

  function applySelection() {
    for (const p of pillars) {
      const isSel = p.station.id === selectedId
      p.tip.scale.setScalar(isSel ? p.baseTipScale * 1.9 : p.baseTipScale)
    }
    selectedPillar = pillars.find((p) => p.station.id === selectedId) ?? null
    if (selectedPillar) {
      selectionHalo.visible = true
      selectionHalo.material.opacity = 0.55
      selectionHalo.scale.setScalar(selectedPillar.baseTipScale * 3.4)
      selectionHalo.position.copy(selectedPillar.tip.position)
    } else {
      selectionHalo.visible = false
      selectionHalo.material.opacity = 0
    }
  }

  // ---- interaction (hover + click, distinguished from orbit drags) ----
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  let hovered: Pillar | null = null
  let downX = 0
  let downY = 0
  let dragging = false

  function pick(clientX: number, clientY: number): Pillar | null {
    const rect = renderer.domElement.getBoundingClientRect()
    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointer, camera)
    // Earth is in the target list so it occludes: a station on the far side
    // of the globe intersects behind the sphere and must not be pickable.
    const hits = raycaster.intersectObjects(pickTargets, false)
    if (!hits.length || hits[0].object === earth) return null
    const id = hits[0].object.userData.stationId as string
    return pillars.find((p) => p.station.id === id) ?? null
  }

  function onPointerDown(e: PointerEvent) {
    downX = e.clientX
    downY = e.clientY
    dragging = false
    // Touch pinch should always zoom; the wheel gate above only manages mice.
    if (e.pointerType === 'touch') controls.enableZoom = true
  }

  function onPointerMove(e: PointerEvent) {
    if (e.buttons !== 0 && Math.hypot(e.clientX - downX, e.clientY - downY) > 4) dragging = true
    const hit = pick(e.clientX, e.clientY)
    if (hit !== hovered) {
      hovered = hit
      renderer.domElement.style.cursor = hit ? 'pointer' : 'grab'
    }
    handlers.onHover(hit ? hit.station : null, e.clientX, e.clientY)
  }

  function onPointerUp(e: PointerEvent) {
    // Suppress selection after an orbit drag — on touch `buttons` may stay 0
    // during the move, so also reject by total travel from the press. Always
    // clear the drag flag, or the ambient spin would stay paused forever.
    const wasDrag = dragging || Math.hypot(e.clientX - downX, e.clientY - downY) > 6
    dragging = false
    if (wasDrag) return
    const hit = pick(e.clientX, e.clientY)
    if (hit) handlers.onSelect(hit.station.id)
  }

  function onPointerLeave() {
    hovered = null
    dragging = false
    handlers.onHover(null, 0, 0)
  }

  const dom = renderer.domElement
  dom.style.cursor = 'grab'
  dom.addEventListener('pointerdown', onPointerDown)
  dom.addEventListener('pointermove', onPointerMove)
  dom.addEventListener('pointerup', onPointerUp)
  dom.addEventListener('pointerleave', onPointerLeave)

  // ---- animation loop, driven only while active + on-screen ----
  const clock = new THREE.Clock()
  let rafId = 0
  let active = true
  let running = false

  function frame() {
    rafId = requestAnimationFrame(frame)
    const dt = clock.getDelta()
    const t = clock.elapsedTime

    if (!reducedMotion && !dragging) globeGroup.rotation.y += SPIN_SPEED * dt
    controls.update()

    // Flood pings expand and fade on a ~2.6s loop.
    for (const p of pillars) {
      if (!p.ring) continue
      const mat = p.ring.material as THREE.MeshBasicMaterial
      if (reducedMotion) {
        p.ring.scale.setScalar(1.6)
        mat.opacity = 0.5
      } else {
        const phase = (t / 2.6) % 1
        p.ring.scale.setScalar(1 + phase * 2.6)
        mat.opacity = 0.7 * (1 - phase)
      }
    }

    // Gently pulse the selected tip so the eye keeps finding it.
    if (selectedPillar && !reducedMotion) {
      const pulse = 1 + Math.sin(t * 3) * 0.12
      selectedPillar.tip.scale.setScalar(selectedPillar.baseTipScale * 1.9 * pulse)
    }

    renderer.render(scene, camera)
  }

  function updateRunning() {
    const shouldRun = active
    if (shouldRun && !running) {
      running = true
      clock.getDelta() // drop the gap so we don't jump on resume
      rafId = requestAnimationFrame(frame)
    } else if (!shouldRun && running) {
      running = false
      cancelAnimationFrame(rafId)
    }
  }
  updateRunning()

  function resize() {
    const w = container.clientWidth
    const h = container.clientHeight || 1
    renderer.setSize(w, h)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }

  const onContextLost = (e: Event) => e.preventDefault()
  dom.addEventListener('webglcontextlost', onContextLost)

  return {
    setStations(stations) {
      buildPillars(stations)
    },
    setSelected(id) {
      selectedId = id
      applySelection()
    },
    setReducedMotion(reduced) {
      reducedMotion = reduced
    },
    setActive(next) {
      active = next
      updateRunning()
    },
    resize,
    dispose() {
      cancelAnimationFrame(rafId)
      running = false
      container.removeEventListener('wheel', onWheelGate, { capture: true })
      dom.removeEventListener('pointerdown', onPointerDown)
      dom.removeEventListener('pointermove', onPointerMove)
      dom.removeEventListener('pointerup', onPointerUp)
      dom.removeEventListener('pointerleave', onPointerLeave)
      dom.removeEventListener('webglcontextlost', onContextLost)
      controls.dispose()
      disposePillars()
      selectionHalo.material.dispose()
      glowTexture.dispose()
      scene.traverse((obj) => {
        const any = obj as THREE.Mesh | THREE.Points | THREE.LineSegments
        if ('geometry' in any && any.geometry) any.geometry.dispose()
        const mat = (any as THREE.Mesh).material
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose())
        else if (mat) (mat as THREE.Material).dispose()
      })
      renderer.dispose()
      if (dom.parentNode === container) container.removeChild(dom)
    },
  }
}
