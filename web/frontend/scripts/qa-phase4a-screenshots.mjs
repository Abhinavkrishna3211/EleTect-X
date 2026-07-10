import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'qa', 'phase4a')
fs.mkdirSync(outDir, { recursive: true })

const baseUrl = process.env.QA_BASE_URL || 'http://localhost:5183'
const email = process.env.QA_STAFF_EMAIL
const password = process.env.QA_STAFF_PASSWORD

if (!email || !password) {
  console.error('Set QA_STAFF_EMAIL and QA_STAFF_PASSWORD (a staff login) before running.')
  process.exit(1)
}

const viewports = [
  { tag: 'desktop', width: 1440, height: 900 },
  { tag: 'mobile', width: 390, height: 844 },
]

async function signIn(page) {
  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('Email').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.getByRole('heading', { name: /Sector 7/ }).waitFor({ state: 'visible', timeout: 15000 })
  // Give the CARTO tiles and pins a moment to paint before capturing.
  await page.waitForTimeout(2500)
}

async function run() {
  const browser = await chromium.launch()
  for (const vp of viewports) {
    const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height } })
    const page = await context.newPage()
    await signIn(page)

    await page.screenshot({ path: path.join(outDir, `overview-${vp.tag}.png`), fullPage: true })
    console.log('overview', vp.tag, 'ok')

    // Select a node via the alerts feed to open the digital-twin panel.
    await page.getByRole('button', { name: /Wild boar/ }).first().click()
    await page.getByText('digital twin').waitFor({ state: 'visible', timeout: 8000 })
    await page.waitForTimeout(600)
    await page.screenshot({ path: path.join(outDir, `overview-node-${vp.tag}.png`), fullPage: true })
    console.log('overview-node', vp.tag, 'ok')

    await context.close()
  }
  await browser.close()
}

run().catch((err) => {
  console.error(err)
  process.exit(1)
})
