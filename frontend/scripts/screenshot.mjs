// Capture real screenshots of the deployed Tideline dashboard for the README.
//
// This is a convenience for once a deploy exists — it is NOT wired into the
// build or CI. One-time setup, then run:
//
//   npm  install -D playwright        # from the frontend/ directory
//   npx  playwright install chromium
//   TIDELINE_URL=https://your-app.example node scripts/screenshot.mjs
//
// It writes docs/screenshots/{dashboard,dashboard-dark,mobile}.png, replacing
// the committed images with captures of the live app.

import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { chromium } from 'playwright'

// TODO (human): set the deployed URL (see DEPLOY.md), or pass TIDELINE_URL.
const URL = process.env.TIDELINE_URL ?? 'TODO_HUMAN_DEPLOYED_URL'

const OUT_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..', 'docs', 'screenshots')

// Give the map tiles, chart, and first NOAA fetch time to settle before capture.
const SETTLE_MS = 3500

const SHOTS = [
  { file: 'dashboard.png', width: 1440, height: 900, colorScheme: 'light' },
  { file: 'dashboard-dark.png', width: 1440, height: 900, colorScheme: 'dark' },
  { file: 'mobile.png', width: 390, height: 844, colorScheme: 'light' },
]

if (URL.startsWith('TODO_HUMAN')) {
  console.error('Set TIDELINE_URL to the deployed app URL first (see DEPLOY.md).')
  process.exit(1)
}

const browser = await chromium.launch()
try {
  for (const { file, width, height, colorScheme } of SHOTS) {
    const context = await browser.newContext({
      viewport: { width, height },
      colorScheme,
      deviceScaleFactor: 2,
    })
    const page = await context.newPage()
    await page.goto(URL, { waitUntil: 'networkidle' })
    await page.waitForTimeout(SETTLE_MS)
    const path = resolve(OUT_DIR, file)
    await page.screenshot({ path })
    console.log(`wrote ${path}`)
    await context.close()
  }
} finally {
  await browser.close()
}
