import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'qa', 'phase2')
fs.mkdirSync(outDir, { recursive: true })

const builtBaseUrl = process.env.QA_BASE_URL || 'http://localhost:5183'
const designBaseUrl = process.env.QA_DESIGN_URL || 'http://localhost:4599'
const designFileUrl = `${designBaseUrl}/EleTect%20Platform.dc.html`

const pages = [
  { slug: 'home', route: '/', hash: 'home', label: 'Home' },
  { slug: 'technology', route: '/technology', hash: 'technology', label: 'Technology' },
  { slug: 'solutions', route: '/solutions', hash: 'solutions', label: 'Solutions' },
  { slug: 'deployments', route: '/deployments', hash: 'deployments', label: 'Deployments' },
  { slug: 'research', route: '/research', hash: 'research', label: 'Research' },
  { slug: 'about', route: '/about', hash: 'about', label: 'About' },
  { slug: 'contact', route: '/contact', hash: 'contact', label: 'Contact' },
  { slug: 'stay-safe', route: '/stay-safe', hash: 'staysafe', label: 'Stay Safe' },
]

const viewports = [
  { tag: 'desktop', width: 1440, height: 900 },
  { tag: 'mobile', width: 390, height: 844 },
]

const only = process.argv.slice(2)
const targetPages = only.length ? pages.filter((p) => only.includes(p.slug)) : pages

async function shootBuilt(browser) {
  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })
    for (const p of targetPages) {
      await page.goto(`${builtBaseUrl}${p.route}`, { waitUntil: 'networkidle' })
      const main = page.locator('main').first()
      await main.waitFor({ state: 'visible' })
      const outFile = path.join(outDir, `${p.slug}-built-${vp.tag}.png`)
      await main.screenshot({ path: outFile })
      console.log('built', p.slug, vp.tag, 'ok')
    }
    await page.close()
  }
}

async function shootDesign(browser) {
  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })
    for (const p of targetPages) {
      await page.goto(`${designFileUrl}#/${p.hash}`, { waitUntil: 'load' })
      const section = page.locator(`[data-screen-label="${p.label}"]`).first()
      await section.waitFor({ state: 'visible' })
      const outFile = path.join(outDir, `${p.slug}-design-${vp.tag}.png`)
      await section.screenshot({ path: outFile })
      console.log('design', p.slug, vp.tag, 'ok')
    }
    await page.close()
  }
}

const browser = await chromium.launch()
await shootBuilt(browser)
await shootDesign(browser)
await browser.close()
console.log('done')
