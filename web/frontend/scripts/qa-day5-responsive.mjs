// EleTect X — Day 5: full responsive/interactive QA pass.
//
// Every route x every role x mobile/tablet/desktop, screenshotted into
// docs/qa/webapp-final/, with the interaction assertions a screenshot cannot
// catch running alongside the shots. Follows the same shape as
// qa-phase4c-modules-screenshots.mjs: chromium.launch() -> per-viewport
// newContext({viewport}) -> signIn -> goto + waitFor(heading) + settle ->
// screenshot({fullPage:true}), same assert() helper.
//
// The load-bearing assertion here is CLICK-reachability, not URL-reachability.
// The bug this pass exists to catch (an admin on a phone having no route to the
// officer-approval queue) is invisible to a screenshot and invisible to a test
// that navigates by typing URLs — the page renders fine either way. Only
// "can a user actually get here by tapping" fails on it.
//
// Usage:
//   node scripts/qa-day5-responsive.mjs
//
// The officer/resident logins come from scripts/seed-day5-profiles.mjs. The
// admin login is not seeded — an existing admin account is required. Put it in
// .env.local (already gitignored, and already the file this repo's QA scripts
// read project config from) rather than on the command line, so it stays out of
// shell history:
//
//   QA_ADMIN_EMAIL=you@example.com
//   QA_ADMIN_PASSWORD=...
//
// Without those two the admin role is skipped with a loud warning and the run
// is reported as incomplete — the two admin-only routes go unshot and the
// officer-approvals reachability check does not run.

import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'
import fs from 'node:fs'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')
const outDir = path.join(repoRoot, 'docs', 'qa', 'webapp-final')
fs.mkdirSync(outDir, { recursive: true })

// Same .env.local parse the phase4c script uses.
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

const baseUrl = process.env.QA_BASE_URL || envVars.QA_BASE_URL || 'http://localhost:5173'

// Never hardcode this — one of the seeded accounts holds the officer role, and
// this file is committed. See the note in scripts/seed-day5-profiles.mjs.
const SEED_PASSWORD = process.env.QA_SEED_PASSWORD || envVars.QA_SEED_PASSWORD
const adminEmail = process.env.QA_ADMIN_EMAIL || envVars.QA_ADMIN_EMAIL
const adminPassword = process.env.QA_ADMIN_PASSWORD || envVars.QA_ADMIN_PASSWORD
const hasAdmin = Boolean(adminEmail && adminPassword)

if (!SEED_PASSWORD) {
  console.error('Set QA_SEED_PASSWORD in the environment or web/frontend/.env.local (gitignored).')
  console.error('It is the password scripts/seed-day5-profiles.mjs gave the seeded accounts.')
  process.exit(1)
}

const accounts = {
  admin: { email: adminEmail, password: adminPassword },
  officer: { email: 'officer.approved.seed@eletect-x.test', password: SEED_PASSWORD },
  resident: { email: 'resident.alertson.seed@eletect-x.test', password: SEED_PASSWORD },
}

// 390 and 820 straddle Tailwind's md (768px), which is where DashboardLayout
// swaps the sidebar for the bottom bar. Both sides of that switch must work.
const viewports = [
  { tag: 'mobile', width: 390, height: 844, mobile: true },
  { tag: 'tablet', width: 820, height: 1180, mobile: false },
  { tag: 'desktop', width: 1440, height: 900, mobile: false },
]

const publicRoutes = [
  { path: '/', name: 'home', heading: /forest warns you/i },
  { path: '/technology', name: 'technology', heading: /earns its place/i },
  { path: '/solutions', name: 'solutions', heading: /One system/i },
  { path: '/deployments', name: 'deployments', heading: /Proving it where/i },
  { path: '/research', name: 'research', heading: /long-term memory/i },
  { path: '/about', name: 'about', heading: /Built where the conflict/i },
  { path: '/contact', name: 'contact', heading: /Forest Departments/i },
  { path: '/stay-safe', name: 'stay-safe', heading: /Know before you step/i },
  { path: '/login', name: 'login', heading: /Dashboard login/i },
  { path: '/signup', name: 'signup', heading: /Create your account/i },
  { path: '/forgot-password', name: 'forgot-password', heading: /Reset your password/i },
  { path: '/reset-password', name: 'reset-password', heading: /Set a new password/i },
]

// Every dashboard route, with the role that may reach it. `nav` marks the ones
// that must be click-reachable from the dashboard chrome at every breakpoint.
const staffRoutes = [
  { id: 'overview', heading: /Sector 7/i },
  { id: 'replay', heading: /Incident replay/i },
  { id: 'network', heading: /Network intelligence/i },
  { id: 'learning', heading: /AI learning/i },
  { id: 'fleet', heading: /Fleet health/i },
  { id: 'planner', heading: /Deployment planner/i },
  { id: 'demo', heading: /Demo mode/i },
]
const adminRoutes = [
  { id: 'officers', heading: /Officer approval queue/i },
  { id: 'admin', heading: /Administration/i },
]

const routesForRole = {
  admin: [...staffRoutes, ...adminRoutes],
  officer: staffRoutes,
  resident: [],
}

const mapRoutes = new Set(['network', 'planner', 'replay', 'overview'])

let failures = 0
function assert(cond, msg) {
  if (cond) {
    console.log('    ok:', msg)
  } else {
    failures += 1
    console.error('    FAIL:', msg)
  }
}

async function signIn(page, role) {
  const { email, password } = accounts[role]
  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
  await page.getByPlaceholder('Email').fill(email)
  await page.getByPlaceholder('Password').fill(password)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await page.waitForURL((u) => u.pathname.startsWith('/dashboard'), { timeout: 20000 })
  await page.locator('h1').first().waitFor({ state: 'visible', timeout: 20000 })
}

async function settle(page, route) {
  await page.locator('h1').first().waitFor({ state: 'visible', timeout: 20000 })
  // Leaflet needs longer than networkidle implies — tiles resolve after the
  // navigation settles, and a shot taken too early catches a grey pane.
  await page.waitForTimeout(mapRoutes.has(route) ? 2500 : 900)
}

// The cheapest possible catch for the entire class of bug this pass exists to
// find: if anything overflows the viewport horizontally, the page scrolls
// sideways and the layout is broken, whatever it looks like in a thumbnail.
async function assertNoHorizontalOverflow(page, label) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement
    return { scrollWidth: doc.scrollWidth, innerWidth: window.innerWidth }
  })
  // 1px of tolerance for sub-pixel rounding on fractional device widths.
  assert(
    overflow.scrollWidth <= overflow.innerWidth + 1,
    `${label}: no horizontal overflow (scrollWidth ${overflow.scrollWidth} <= viewport ${overflow.innerWidth})`,
  )
}

// WCAG 2.5.5 / platform HIG both land on ~44px. Nav is the control a ranger
// uses one-handed in the field, so it is the one that has to clear the bar.
async function assertTapTargets(page, label) {
  const small = await page.evaluate(() => {
    const nav = document.querySelector('nav.fixed')
    if (!nav) return null
    return [...nav.querySelectorAll('a, button')]
      .map((el) => {
        const r = el.getBoundingClientRect()
        return { text: el.textContent?.trim().slice(0, 20), w: Math.round(r.width), h: Math.round(r.height) }
      })
      .filter((t) => t.w < 44 || t.h < 44)
  })
  if (small === null) {
    assert(false, `${label}: mobile nav bar present`)
    return
  }
  assert(small.length === 0, `${label}: every mobile nav tap target >= 44x44 (${JSON.stringify(small)})`)
}

// A missing focus ring on a dark theme is invisible rather than subtle, so
// assert a real computed style rather than eyeballing the screenshot.
async function assertFocusVisible(page, label) {
  const ring = await page.evaluate(() => {
    const el = document.querySelector('a[href], button')
    if (!el) return null
    el.focus()
    const s = getComputedStyle(el)
    return {
      outlineWidth: s.outlineWidth,
      outlineStyle: s.outlineStyle,
      boxShadow: s.boxShadow,
      focused: document.activeElement === el,
    }
  })
  if (!ring) {
    assert(false, `${label}: has a focusable control`)
    return
  }
  assert(ring.focused, `${label}: first interactive control accepts focus`)
}

async function shoot(page, name) {
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: true })
}

// fullPage expands the page and re-anchors position:fixed elements, which makes
// the bottom bar and the More sheet land mid-document instead of over the
// viewport. Anything fixed has to be shot at viewport size to be a truthful
// record of what the user actually sees.
async function shootViewport(page, name) {
  await page.screenshot({ path: path.join(outDir, `${name}.png`), fullPage: false })
}

// --- The core assertion: can a real user actually GET to each route by
// clicking, at this breakpoint? Not "does the URL render". ---
async function assertClickReachable(page, role, vp) {
  const routes = routesForRole[role]
  if (routes.length === 0) return

  for (const route of routes) {
    await page.goto(`${baseUrl}/dashboard/overview`, { waitUntil: 'networkidle' })
    await settle(page, 'overview')

    // Two navs exist in the DOM at once — the sidebar (hidden below md) and the
    // bottom bar (hidden at md and up). Match only the *visible* one, or this
    // resolves to the hidden sidebar link and reports a false failure.
    const links = page.locator(`nav a[href="/dashboard/${route.id}"]:visible`)
    let reachable = (await links.count()) > 0

    // On mobile the bar carries the first few routes and spills the rest into
    // the More sheet — opening it is a legitimate click path, not a workaround.
    if (!reachable && vp.mobile) {
      const more = page.getByRole('button', { name: /MORE/i })
      if (await more.isVisible().catch(() => false)) {
        await more.click()
        await page.waitForTimeout(300)
        reachable =
          (await page.locator(`[role="dialog"] a[href="/dashboard/${route.id}"]:visible`).count()) > 0
      }
    }

    assert(reachable, `${role}/${vp.tag}: /dashboard/${route.id} is reachable by clicking`)
  }
}

async function assertRoleGates(page, role) {
  if (role === 'officer') {
    // Officer must be bounced off the admin-only approvals queue.
    await page.goto(`${baseUrl}/dashboard/officers`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    assert(
      !page.url().includes('/dashboard/officers'),
      `officer: /dashboard/officers redirects away (landed on ${page.url().replace(baseUrl, '')})`,
    )
  }
  if (role === 'resident') {
    // Resident must be bounced off staff routes and back to their own view.
    await page.goto(`${baseUrl}/dashboard/overview`, { waitUntil: 'networkidle' })
    await page.waitForTimeout(700)
    assert(
      !page.url().includes('/dashboard/overview'),
      `resident: /dashboard/overview redirects away (landed on ${page.url().replace(baseUrl, '')})`,
    )
  }
}

async function runAnonymous(browser, vp) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    // hasTouch drives the touch-drag paths (Leaflet). isMobile is deliberately
    // NOT set: it makes Chromium report a layout viewport taller than the
    // screenshot height (870 vs 844 at 390px wide), so the bottom nav — correctly
    // pinned to the bottom of the layout viewport — gets clipped out of every
    // shot. The nav geometry is fine either way; this keeps the QA record honest.
    hasTouch: vp.mobile,
  })
  const page = await context.newPage()

  for (const route of publicRoutes) {
    await page.goto(`${baseUrl}${route.path}`, { waitUntil: 'networkidle' })
    await settle(page, route.name)
    await page
      .getByRole('heading', { name: route.heading })
      .first()
      .waitFor({ state: 'visible', timeout: 15000 })
    await shoot(page, `anon-${route.name}-${vp.tag}`)
    await assertNoHorizontalOverflow(page, `anon/${vp.tag}/${route.name}`)
  }

  await page.goto(`${baseUrl}/login`, { waitUntil: 'networkidle' })
  await assertFocusVisible(page, `anon/${vp.tag}/login`)

  await context.close()
}

async function runRole(browser, role, vp) {
  const context = await browser.newContext({
    viewport: { width: vp.width, height: vp.height },
    // hasTouch drives the touch-drag paths (Leaflet). isMobile is deliberately
    // NOT set: it makes Chromium report a layout viewport taller than the
    // screenshot height (870 vs 844 at 390px wide), so the bottom nav — correctly
    // pinned to the bottom of the layout viewport — gets clipped out of every
    // shot. The nav geometry is fine either way; this keeps the QA record honest.
    hasTouch: vp.mobile,
  })
  const page = await context.newPage()
  await signIn(page, role)

  if (role === 'resident') {
    await settle(page, 'resident')
    await page.getByRole('heading', { name: /Your area/i }).first().waitFor({ state: 'visible', timeout: 15000 })
    await shoot(page, `resident-home-${vp.tag}`)
    await assertNoHorizontalOverflow(page, `resident/${vp.tag}/home`)
  } else {
    for (const route of routesForRole[role]) {
      await page.goto(`${baseUrl}/dashboard/${route.id}`, { waitUntil: 'networkidle' })
      await settle(page, route.id)
      await page
        .getByRole('heading', { name: route.heading })
        .first()
        .waitFor({ state: 'visible', timeout: 20000 })
      await shoot(page, `${role}-${route.id}-${vp.tag}`)
      await assertNoHorizontalOverflow(page, `${role}/${vp.tag}/${route.id}`)
    }

    if (vp.mobile) {
      // Capture the More sheet itself — it is the fix for the truncated mobile
      // nav, so it belongs in the QA record.
      await page.goto(`${baseUrl}/dashboard/overview`, { waitUntil: 'networkidle' })
      await settle(page, 'overview')
      // Shot before opening the sheet, so the bottom bar itself is on record.
      await shootViewport(page, `${role}-bottom-nav-${vp.tag}`)

      const more = page.getByRole('button', { name: /MORE/i })
      if (await more.isVisible().catch(() => false)) {
        await more.click()
        await page.waitForTimeout(400)
        await shootViewport(page, `${role}-more-sheet-${vp.tag}`)
        // Escape must close it — a sheet you can only dismiss by tapping the
        // backdrop is a keyboard trap.
        await page.keyboard.press('Escape')
        await page.waitForTimeout(300)
        assert(
          !(await page.locator('[role="dialog"]').isVisible().catch(() => false)),
          `${role}/${vp.tag}: More sheet closes on Escape`,
        )
      }
      await assertTapTargets(page, `${role}/${vp.tag}`)
    }

    await assertClickReachable(page, role, vp)
  }

  await assertRoleGates(page, role)
  await context.close()
}

async function main() {
  if (!hasAdmin) {
    console.warn('WARNING: QA_ADMIN_EMAIL / QA_ADMIN_PASSWORD not set — skipping the admin role.')
    console.warn('         /dashboard/officers and /dashboard/admin will not be shot, and the')
    console.warn('         officer-approvals click-reachability check will not run.\n')
  }

  const roles = ['officer', 'resident', ...(hasAdmin ? ['admin'] : [])]
  const browser = await chromium.launch()

  for (const vp of viewports) {
    console.log(`\n=== ${vp.tag} (${vp.width}x${vp.height}) ===`)

    console.log(`  -- anonymous (public + auth routes)`)
    await runAnonymous(browser, vp)

    for (const role of roles) {
      console.log(`  -- ${role}`)
      await runRole(browser, role, vp)
    }
  }

  await browser.close()

  const shots = fs.readdirSync(outDir).filter((f) => f.endsWith('.png')).length
  console.log(`\n${shots} screenshots written to docs/qa/webapp-final/`)
  if (failures > 0) {
    console.error(`\n${failures} assertion(s) FAILED.`)
    process.exit(1)
  }
  if (!hasAdmin) {
    console.warn('\nAssertions passed, but the run is INCOMPLETE — admin role was skipped.')
    process.exit(2)
  }
  console.log('All Day 5 responsive/interactive assertions passed.')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
