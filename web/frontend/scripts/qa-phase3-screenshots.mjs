import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'qa', 'phase3')
fs.mkdirSync(outDir, { recursive: true })

// Same .env.local parse the other QA scripts use, so the password is set once.
const envPath = path.join(__dirname, '..', '.env.local')
const envVars = fs.existsSync(envPath)
  ? Object.fromEntries(
      fs
        .readFileSync(envPath, 'utf8')
        .split('\n')
        .map((l) => l.trim())
        .filter((l) => l && !l.startsWith('#') && l.includes('='))
        .map((l) => {
          const i = l.indexOf('=')
          return [l.slice(0, i), l.slice(i + 1)]
        }),
    )
  : {}

const baseUrl = process.env.QA_BASE_URL || 'http://localhost:5183'

// Never hardcode this. The signups below are throwaway `public`-role accounts, so
// a leak is far less serious than the seed script's officer-role account — but a
// committed credential is a committed credential, and this file is public.
const SEED_PASSWORD = process.env.QA_SEED_PASSWORD || envVars.QA_SEED_PASSWORD

if (!SEED_PASSWORD || SEED_PASSWORD.length < 16) {
  console.error('Set QA_SEED_PASSWORD (>= 16 chars) in the environment or web/frontend/.env.local.')
  process.exit(1)
}

const viewports = [
  { tag: 'desktop', width: 1440, height: 900 },
  { tag: 'mobile', width: 390, height: 844 },
]

async function shootStaticFlows(browser) {
  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })

    await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
    await page.screenshot({ path: path.join(outDir, `login-${vp.tag}.png`) })
    console.log('login', vp.tag, 'ok')

    await page.goto(`${baseUrl}/signup`, { waitUntil: 'networkidle' })
    await page.screenshot({ path: path.join(outDir, `signup-resident-${vp.tag}.png`) })
    console.log('signup-resident', vp.tag, 'ok')

    await page.getByRole('button', { name: 'Forest Officer' }).click()
    await page.getByPlaceholder('Department (e.g. Kerala Forest Department)').waitFor({ state: 'visible' })
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(outDir, `signup-officer-${vp.tag}.png`) })
    console.log('signup-officer', vp.tag, 'ok')

    await page.goto(`${baseUrl}/forgot-password`, { waitUntil: 'networkidle' })
    await page.screenshot({ path: path.join(outDir, `forgot-password-${vp.tag}.png`) })
    console.log('forgot-password', vp.tag, 'ok')

    await page.getByPlaceholder('Email').fill('qa-test@example.com')
    await page.getByRole('button', { name: 'Send reset link' }).click()
    await page.getByText('Check your inbox.').waitFor({ state: 'visible' })
    await page.screenshot({ path: path.join(outDir, `forgot-password-sent-${vp.tag}.png`) })
    console.log('forgot-password-sent', vp.tag, 'ok')

    await page.goto(`${baseUrl}/reset-password`, { waitUntil: 'networkidle' })
    await page.screenshot({ path: path.join(outDir, `reset-password-${vp.tag}.png`) })
    console.log('reset-password', vp.tag, 'ok')

    await page.close()
  }
}

async function shootResidentFlow(browser) {
  const stamp = Date.now()
  const email = `qa-resident-${stamp}@example.com`
  const password = SEED_PASSWORD

  for (const vp of viewports) {
    const page = await browser.newPage({ viewport: { width: vp.width, height: vp.height } })

    await page.goto(`${baseUrl}/signup`, { waitUntil: 'networkidle' })
    await page.getByPlaceholder('Full name').fill('QA Resident')
    await page.getByPlaceholder('Phone number (+91…)').fill('+919999999999')
    await page.getByPlaceholder('Email').fill(email)
    await page.getByPlaceholder('Create a password').fill(password)
    await page.getByRole('button', { name: 'Sign up' }).click()

    const created = page.getByText('Account created.')
    const signupError = page.locator('form p.text-brand-red')
    await Promise.race([
      created.waitFor({ state: 'visible' }),
      signupError.waitFor({ state: 'visible' }),
    ])

    if (await signupError.isVisible().catch(() => false)) {
      console.log('resident signup skipped:', await signupError.textContent())
      await page.close()
      continue
    }

    await page.screenshot({ path: path.join(outDir, `signup-resident-success-${vp.tag}.png`) })
    console.log('signup-resident-success', vp.tag, 'ok')

    await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
    await page.getByPlaceholder('Email').fill(email)
    await page.getByPlaceholder('Password').fill(password)
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForURL(`${baseUrl}/dashboard`, { timeout: 10000 }).catch(() => {})

    const areaHeading = page.getByText('Your area tonight')
    if (!(await areaHeading.isVisible().catch(() => false))) {
      console.log('resident dashboard skipped: did not reach dashboard for', vp.tag)
      await page.close()
      continue
    }

    await page.screenshot({ path: path.join(outDir, `dashboard-resident-${vp.tag}.png`) })
    console.log('dashboard-resident', vp.tag, 'ok')

    await page.getByText('SMS alerts').click()
    await page.waitForTimeout(500)
    await page.screenshot({ path: path.join(outDir, `dashboard-resident-sms-on-${vp.tag}.png`) })
    console.log('dashboard-resident-sms-on', vp.tag, 'ok')

    await page.close()
  }
}

const browser = await chromium.launch()
await shootStaticFlows(browser)
await shootResidentFlow(browser)
await browser.close()
console.log('done')
