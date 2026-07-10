import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'qa', 'phase4b')
fs.mkdirSync(outDir, { recursive: true })

const baseUrl = process.env.QA_BASE_URL || 'http://localhost:5183'
const email = process.env.QA_STAFF_EMAIL
const password = process.env.QA_STAFF_PASSWORD

if (!email || !password) {
  console.error('Set QA_STAFF_EMAIL and QA_STAFF_PASSWORD (a staff login) before running.')
  console.error('Apply web/backend/schema.sql (corridor column) + seed-4b.sql first, or the views render empty.')
  process.exit(1)
}

const viewports = [
  { tag: 'desktop', width: 1440, height: 900 },
  { tag: 'mobile', width: 390, height: 844 },
]

const views = [
  { id: 'replay', heading: /Incident replay/, name: 'replay' },
  { id: 'network', heading: /Network intelligence/, name: 'corridor' },
  { id: 'learning', heading: /AI learning/, name: 'learning' },
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
  await page.waitForTimeout(1200) // let the map / chart paint
}

// A short frame sequence a couple hundred ms apart — a static shot can't prove
// motion, so we capture the animation actually advancing.
async function captureFrames(page, prefix, count, gapMs) {
  for (let i = 0; i < count; i++) {
    await page.screenshot({ path: path.join(outDir, `${prefix}-f${i}.png`) })
    await page.waitForTimeout(gapMs)
  }
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
      await gotoView(page, views[0])
      await page.getByRole('button', { name: /Play|Replay/ }).click()
      await captureFrames(page, 'replay-scrub', 5, 260)
      console.log('replay-scrub frames ok')

      await gotoView(page, views[1])
      await captureFrames(page, 'corridor-pulse', 5, 420)
      console.log('corridor-pulse frames ok')
    }

    await context.close()
  }
  await browser.close()
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
