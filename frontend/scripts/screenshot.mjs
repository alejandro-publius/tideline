// Capture real screenshots of the deployed Tideline dashboard for the README.
//
// This is a convenience for once a deploy exists — it is NOT wired into the
// build or CI. One-time setup, then run:
//
//   npm  install -D playwright        # from the frontend/ directory
//   npx  playwright install chromium
//   TIDELINE_URL=https://your-app.example node scripts/screenshot.mjs
//
// It writes docs/screenshots/{globe,dashboard,dashboard-dark,mobile}.png,
// replacing the committed images with captures of the live app.

import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { chromium } from 'playwright'

// TODO (human): set the deployed URL (see DEPLOY.md), or pass TIDELINE_URL.
const URL = process.env.TIDELINE_URL ?? 'TODO_HUMAN_DEPLOYED_URL'

const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs', 'screenshots')

// Give the map tiles, chart, first NOAA fetch, and globe time to settle.
const SETTLE_MS = 3500

const SHOTS = [
  { file: 'dashboard.png', width: 1440, height: 900, colorScheme: 'light' },
  { file: 'dashboard-dark.png', width: 1440, height: 900, colorScheme: 'dark' },
  { file: 'mobile.png', width: 390, height: 844, colorScheme: 'light' },
  // hero-only capture of the 3D surge globe (clipped, so no map below)
  { file: 'globe.png', width: 1440, height: 900, colorScheme: 'dark', clip: '.globe-hero' },
]

if (URL.startsWith('TODO_HUMAN')) {
  console.error('Set TIDELINE_URL to the deployed app URL first (see DEPLOY.md).')
  process.exit(1)
}

const browser = await chromium.launch()
try {
  for (const { file, width, height, colorScheme, clip } of SHOTS) {
    const context = await browser.newContext({
      viewport: { width, height },
      colorScheme,
      deviceScaleFactor: 2,
    })
    const page = await context.newPage()
    await page.goto(URL, { waitUntil: 'networkidle' })
    // The globe is lazy-loaded WebGL; without this wait a capture can race the
    // chunk download and show only the loading banner. Headless environments
    // without WebGL never mount the canvas — fall through after a short wait
    // rather than failing the whole run.
    const globeReady = await page
      .waitForSelector('.globe-canvas canvas', { timeout: 15_000 })
      .then(() => true)
      .catch(() => (console.warn(`${file}: globe canvas never appeared (no WebGL?)`), false))
    await page.waitForTimeout(SETTLE_MS)
    const path = resolve(OUT_DIR, file)
    if (clip) {
      // don't overwrite the committed globe shot with a fallback banner
      if (!globeReady) {
        console.warn(`${file}: skipped — globe never rendered`)
        await context.close()
        continue
      }
      await page.locator(clip).screenshot({ path })
    } else {
      await page.screenshot({ path })
    }
    console.log(`wrote ${path}`)
    await context.close()
  }
} finally {
  await browser.close()
}
