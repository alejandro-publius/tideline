# ADR 0007: Render the surge globe imperatively, outside React, in a lazy chunk

**Status:** accepted (July 2026)

## Context

The dashboard gained a 3D hero: a WebGL globe where every station is a pillar
whose height and color encode the live surge residual. Three ways to build it
were on the table:

1. A React renderer for three.js (`@react-three/fiber`), reconciling the scene
   graph declaratively.
2. Imperative three.js behind a thin React shell.
3. No 3D at all — keep the 2D map as the only spatial view.

Two hard constraints shaped the choice. First, three.js is ~600 kB minified —
an order of magnitude larger than any other dependency — and the app's first
paint budget was already spent deliberately (split vendor chunks, skeletons).
Second, the scene changes on a completely different rhythm than the DOM: the
render loop mutates rotation and animation state 60 times a second, while the
*data* (13 stations' surge values) changes every five minutes.

## Decision

Imperative three.js (`globeScene.ts`) behind a thin React shell (`Globe.tsx`),
lazy-loaded (`GlobeHero.tsx` wraps it in `lazy` + `Suspense` + an error
boundary), with the pure math split into `lib/globe.ts`:

- **Build once, mutate on change.** The scene is constructed a single time;
  React effects forward data/selection/motion changes to narrow setter methods
  (`setStations`, `setSelected`, `setReducedMotion`). No virtual-DOM diffing
  runs at animation frequency, and disposal is one explicit code path.
- **Lazy chunk.** `three` + the coastline TopoJSON live in their own vendor
  chunk, downloaded only when the hero mounts. First paint never pays for 3D;
  a failed chunk load degrades to the fallback banner, not a white screen.
- **Pure math stays out.** Projection, the confidence color ramp, and pillar
  sizing are plain functions in `lib/globe.ts` with no `three` import — they
  unit-test in jsdom like the rest of `lib/`, and the eager bundle (the hero's
  anomaly chip needs the color ramp) pays only for arithmetic.
- **The page must win conflicts with the scene.** OrbitControls defaults trap
  page scrolling on a full-width hero, so the canvas keeps `touch-action:
  pan-y` (vertical swipes scroll, horizontal drags orbit) and wheel-zoom
  requires a held modifier key.

`@react-three/fiber` was rejected as a second framework to learn and audit for
what is one scene with ~50 objects; a declarative reconciler earns its cost
when component trees compose 3D content, which is not this app. Rendering is
also suspended whenever the hero is off-screen or the tab is hidden — the same
"don't work when nobody's looking" ethos as the dashboard's visibility-gated
polling.

## Consequences

- The globe costs nothing until it's looked at, and nothing again when it's
  scrolled away — `IntersectionObserver` + `visibilitychange` gate the loop.
- Imperative scene code carries manual disposal duties (geometries, materials,
  textures, listeners); `dispose()` is the contract and StrictMode's
  double-mount exercises it in development.
- The encoding (pLDDT-style confidence ramp: calm blue → storm orange) is an
  explicit homage to AlphaFold and is documented in `lib/globe.ts` where the
  stops are defined; the legend gradient in CSS mirrors those stops and the
  two must move together.
- Accessibility is delegated: the globe is pointer-only, and every action it
  offers (select a station, read a surge) has a keyboard-reachable equivalent
  (the station dropdown, the tiles, the map).
