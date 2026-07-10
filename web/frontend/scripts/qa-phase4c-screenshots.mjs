import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'qa', 'phase4c')
fs.mkdirSync(outDir, { recursive: true })

const baseUrl = process.env.QA_BASE_URL || 'http://localhost:5183'
const email = process.env.QA_STAFF_EMAIL
const password = process.env.QA_STAFF_PASSWORD

if (!email || !password) {
  console.error('Set QA_STAFF_EMAIL and QA_STAFF_PASSWORD (a staff login) before running.')
  console.error('Apply web/backend/schema.sql + seed-4b.sql first, or the incident views render empty.')
  process.exit(1)
}

const viewports = [
  { tag: 'desktop', width: 1440, height: 900 },
  { tag: 'mobile', width: 390, height: 844 },
]

const views = [
  { id: 'overview', heading: /Sector 7/, name: 'overview' },
  { id: 'replay', heading: /Incident replay/, name: 'replay' },
  { id: 'network', heading: /Network intelligence/, name: 'corridor' },
]

async function signIn(page) {
  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('Email').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('heading', { name: /Sector 7/ }).waitFor({ state: 'visible', timeout: 15000 })
}

async function gotoView(page, view) {
  await page.goto(`${baseUrl}/dashboard/${view.id}`, { waitUntil: 'networkidle' })
  await page.getByRole('heading', { name: view.heading }).waitFor({ state: 'visible', timeout: 15000 })
  // Let the basemap rasters land before shooting — a half-tiled map proves nothing.
  await page.waitForTimeout(2500)
}

// A short frame sequence a couple hundred ms apart — a static shot can't prove
// motion, so we capture the animation actually advancing.
async function captureFrames(page, prefix, count, gapMs) {
  for (let i = 0; i < count; i++) {
    await page.screenshot({ path: path.join(outDir, `${prefix}-f${i}.png`) })
    await page.waitForTimeout(gapMs)
  }
}

// The herd marker's screen position, read off the Leaflet icon transform. Proves
// the marker interpolates between nodes instead of snapping onto them.
async function herdTransform(page) {
  return page.evaluate(() => {
    const el = document.querySelector('.et-herd-marker')
    return el ? getComputedStyle(el).transform : null
  })
}

async function run() {
  const browser = await chromium.launch()
  for (const vp of viewports) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } })
    const page = await context.newPage()
    await signIn(page)

    for (const view of views) {
      await gotoView(page, view)
      await page.screenshot({ path: path.join(outDir, `${view.name}-${vp.tag}.png`), fullPage: true })
      console.log(view.name, vp.tag, 'ok')
    }

    // Motion proof (desktop only): Replay scrub advancing + Corridor pulse handoff.
    if (vp.tag === 'desktop') {
      await gotoView(page, views[1])
      await page.getByRole('button', { name: /Play|Replay/ }).click()
      const replayTracks = []
      for (let i = 0; i < 5; i++) {
        await page.screenshot({ path: path.join(outDir, `replay-scrub-f${i}.png`) })
        replayTracks.push(await herdTransform(page))
        await page.waitForTimeout(260)
      }
      console.log('replay-scrub frames ok')
      console.log('replay herd transforms:', replayTracks.join(' | '))

      await gotoView(page, views[2])
      const corridorTracks = []
      for (let i = 0; i < 5; i++) {
        await page.screenshot({ path: path.join(outDir, `corridor-pulse-f${i}.png`) })
        corridorTracks.push(await herdTransform(page))
        await page.waitForTimeout(420)
      }
      console.log('corridor-pulse frames ok')
      console.log('corridor herd transforms:', corridorTracks.join(' | '))
    }

    await context.close()
  }
  await browser.close()
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
