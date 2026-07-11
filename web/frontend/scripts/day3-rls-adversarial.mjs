// EleTect X — Day 3 RLS/RBAC adversarial pass.
// Hits the live Supabase REST API directly (no UI) as (1) a true anonymous
// caller and (2) a freshly signed-up public-role user, and checks that every
// staff/admin-only surface actually rejects both. Read-the-policy-file is not
// enough; this is the live-call proof the completion plan calls for.
//
// Usage:
//   SUPABASE_URL=https://<ref>.supabase.co SUPABASE_ANON_KEY=<anon key> node scripts/day3-rls-adversarial.mjs
//
// Exits non-zero if any check fails, so it can be wired into CI later the same
// way the Playwright smoke suite (Day 6) will be.

const URL_BASE = process.env.SUPABASE_URL
const ANON_KEY = process.env.SUPABASE_ANON_KEY

if (!URL_BASE || !ANON_KEY) {
  console.error('Set SUPABASE_URL and SUPABASE_ANON_KEY environment variables first.')
  process.exit(1)
}

const results = []
function record(name, pass, detail) {
  results.push({ name, pass, detail })
  console.log(`[${pass ? 'PASS' : 'FAIL'}] ${name}${detail ? ' — ' + detail : ''}`)
}

async function rest(path, { token, method = 'GET', body } = {}) {
  const res = await fetch(`${URL_BASE}/rest/v1/${path}`, {
    method,
    headers: {
      apikey: ANON_KEY,
      Authorization: `Bearer ${token ?? ANON_KEY}`,
      'Content-Type': 'application/json',
      ...(method !== 'GET' ? { Prefer: 'return=representation' } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let json = null
  try { json = JSON.parse(text) } catch { /* not json */ }
  return { status: res.status, json, text }
}

async function rpc(name, args, token) {
  return rest(`rpc/${name}`, { token, method: 'POST', body: args })
}

// A direct table read is "blocked" if RLS returns zero rows, or PostgREST
// itself refuses the call (401/403/404). Getting *other people's* rows back
// is the only real failure.
function blockedOrEmpty(r) {
  if (r.status === 401 || r.status === 403 || r.status === 404) return true
  if (r.status === 200 && Array.isArray(r.json) && r.json.length === 0) return true
  return false
}
function rpcRejected(r) {
  if (r.status === 401 || r.status === 403 || r.status === 404) return true
  if (r.status >= 400 && r.json && /not authorized/i.test(JSON.stringify(r.json))) return true
  return false
}

async function main() {
  console.log(`Target: ${URL_BASE}\n`)

  // ---------- 1. Anonymous caller (no signed-in user at all) ----------
  console.log('--- Anonymous (no JWT beyond the anon key) ---')
  for (const table of ['profiles', 'nodes', 'events', 'health', 'maintenance', 'alerts', 'officer_requests', 'demo_node_snapshot']) {
    const r = await rest(`${table}?select=*`)
    record(`anon cannot read ${table}`, blockedOrEmpty(r), `HTTP ${r.status}, ${Array.isArray(r.json) ? r.json.length + ' rows' : r.text.slice(0, 120)}`)
  }
  {
    const r = await rest('public_area_risk?select=*')
    record('anon CAN read public_area_risk (intended)', r.status === 200, `HTTP ${r.status}`)
  }
  for (const [name, args] of [
    ['run_demo_scenario', { p_scenario: 'confirmed_elephant', p_step: 1 }],
    ['reset_demo_data', {}],
    ['demo_touch_node', { p_node: 'S7-01', p_status: 'alert' }],
    ['approve_officer_request', { req_id: 1 }],
    ['reject_officer_request', { req_id: 1 }],
  ]) {
    const r = await rpc(name, args)
    record(`anon cannot call ${name}()`, rpcRejected(r), `HTTP ${r.status}, ${r.text.slice(0, 160)}`)
  }

  // ---------- 2. Freshly signed-up public-role user ----------
  console.log('\n--- Authenticated, role=public (throwaway signup) ---')
  // example.com and most disposable-looking domains get rejected outright by
  // Supabase's signup validation. Default to a real, deliverable address via a
  // Gmail-style +alias (all variants land in the same inbox) so signup actually
  // succeeds; override with SUPABASE_TEST_EMAIL if you'd rather use your own.
  const probeEmail = process.env.SUPABASE_TEST_EMAIL
    ?? `abhinav123krish+day3adversarial${Date.now()}@gmail.com`
  const probePass = 'AdversarialProbe!2026'
  // If SUPABASE_TEST_EMAIL is set, assume that account already exists and is
  // confirmed (e.g. from a previous run of this script) and just sign in —
  // avoids creating a fresh throwaway user, and a fresh signup, every run.
  let token, uid
  if (process.env.SUPABASE_TEST_EMAIL) {
    const email = process.env.SUPABASE_TEST_EMAIL
    const password = process.env.SUPABASE_TEST_PASSWORD ?? probePass
    const signin = await fetch(`${URL_BASE}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { apikey: ANON_KEY, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    const signinJson = await signin.json()
    token = signinJson.access_token
    uid = signinJson.user?.id
    if (!token) console.log(`Sign-in failed (HTTP ${signin.status}): ${JSON.stringify(signinJson).slice(0, 300)}`)
  } else {
    const signup = await fetch(`${URL_BASE}/auth/v1/signup`, {
      method: 'POST',
      headers: { apikey: ANON_KEY, 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: probeEmail, password: probePass, data: { full_name: 'Day3 Adversarial Probe' } }),
    })
    const signupJson = await signup.json()
    token = signupJson.access_token
    uid = signupJson.user?.id

    if (!token) {
      console.log(`Signup did not return a session directly (HTTP ${signup.status}): ${JSON.stringify(signupJson).slice(0, 300)}`)
      console.log(`Account created as ${probeEmail} but needs email confirmation. Confirm it, then re-run with:`)
      console.log(`  $env:SUPABASE_TEST_EMAIL = "${probeEmail}"`)
      console.log('  node scripts\\day3-rls-adversarial.mjs')
      console.log('(that signs in instead of signing up again, and runs the authenticated-role half.)')
    }
  }
  const authToken = token ?? process.env.SUPABASE_TEST_TOKEN

  if (authToken) {
    for (const table of ['nodes', 'events', 'health', 'maintenance', 'alerts', 'demo_node_snapshot']) {
      const r = await rest(`${table}?select=*`, { token: authToken })
      record(`public role cannot read ${table}`, blockedOrEmpty(r), `HTTP ${r.status}, ${Array.isArray(r.json) ? r.json.length + ' rows' : r.text.slice(0, 120)}`)
    }

    // Own profile row: should be readable.
    const ownProfile = await rest(`profiles?select=*`, { token: authToken })
    record('public role CAN read own profile row', ownProfile.status === 200 && Array.isArray(ownProfile.json) && ownProfile.json.length === 1,
      `HTTP ${ownProfile.status}, ${ownProfile.json?.length ?? '?'} rows`)

    // Other people's profile rows: should never appear.
    if (uid) {
      const others = await rest(`profiles?select=*&id=neq.${uid}`, { token: authToken })
      record('public role cannot read OTHER profiles', blockedOrEmpty(others), `HTTP ${others.status}, ${others.json?.length ?? '?'} rows`)
    }

    // Column-privilege escalation attempt: try to grant self admin via direct PATCH.
    const escalate = await rest(`profiles?id=eq.${uid}`, { token: authToken, method: 'PATCH', body: { role: 'admin' } })
    const escalated = escalate.status === 200 && Array.isArray(escalate.json) && escalate.json[0]?.role === 'admin'
    record('public role CANNOT self-promote to admin via PATCH', !escalated, `HTTP ${escalate.status}, ${escalate.text.slice(0, 160)}`)

    // Legitimate self-service column update should still work.
    const legitUpdate = await rest(`profiles?id=eq.${uid}`, { token: authToken, method: 'PATCH', body: { phone: '+919999999999' } })
    record('public role CAN update own phone', legitUpdate.status === 200, `HTTP ${legitUpdate.status}`)

    // officer_requests: none filed by this probe user, so expect empty, not an error.
    const ownRequests = await rest('officer_requests?select=*', { token: authToken })
    record('public role sees only own officer_requests (none filed = empty)', ownRequests.status === 200 && Array.isArray(ownRequests.json) && ownRequests.json.length === 0,
      `HTTP ${ownRequests.status}, ${ownRequests.json?.length ?? '?'} rows`)

    for (const [name, args] of [
      ['run_demo_scenario', { p_scenario: 'confirmed_elephant', p_step: 1 }],
      ['reset_demo_data', {}],
      ['demo_touch_node', { p_node: 'S7-01', p_status: 'alert' }],
      ['approve_officer_request', { req_id: 1 }],
      ['reject_officer_request', { req_id: 1 }],
    ]) {
      const r = await rpc(name, args, authToken)
      record(`public role cannot call ${name}()`, rpcRejected(r), `HTTP ${r.status}, ${r.text.slice(0, 160)}`)
    }

    // ---------- 3. Same account, promoted to officer ----------
    // Requires the probe user's profiles.role to already be set to 'officer'
    // (run the SQL the runbook prints below, once, before this half executes).
    // No new sign-in needed — is_staff()/is_admin() re-check profiles.role live
    // on every call, they don't read it out of the JWT.
    if (process.env.SUPABASE_TEST_AS_OFFICER) {
      console.log('\n--- Same account, role=officer (promoted for boundary test) ---')
      for (const table of ['nodes', 'events', 'health', 'maintenance', 'alerts']) {
        const r = await rest(`${table}?select=*`, { token: authToken })
        record(`officer CAN read ${table}`, r.status === 200, `HTTP ${r.status}, ${Array.isArray(r.json) ? r.json.length + ' rows' : r.text.slice(0, 120)}`)
      }

      // Staff can read nodes, but only admin can write them directly (n_admin_all).
      const writeAttempt = await rest('nodes?id=eq.S7-01', { token: authToken, method: 'PATCH', body: { status: 'offline' } })
      const wrote = writeAttempt.status === 200 && Array.isArray(writeAttempt.json) && writeAttempt.json.length > 0
      record('officer CANNOT write nodes directly (admin-only)', !wrote, `HTTP ${writeAttempt.status}, ${writeAttempt.text.slice(0, 160)}`)

      // The one thing this whole test exists to check: admin-only RPCs stay
      // admin-only even for a legitimate staff member.
      for (const [name, args] of [
        ['approve_officer_request', { req_id: 1 }],
        ['reject_officer_request', { req_id: 1 }],
      ]) {
        const r = await rpc(name, args, authToken)
        record(`officer cannot call ${name}() (admin-only)`, rpcRejected(r), `HTTP ${r.status}, ${r.text.slice(0, 160)}`)
      }

      // Officer SHOULD be able to run Demo Mode (is_staff(), not is_admin());
      // clean up immediately after so no demo row lingers in production.
      const demoRun = await rpc('run_demo_scenario', { p_scenario: 'confirmed_elephant', p_step: 1 }, authToken)
      record('officer CAN call run_demo_scenario() (is_staff, not admin-only)', demoRun.status === 200, `HTTP ${demoRun.status}`)
      const cleanup = await rpc('reset_demo_data', {}, authToken)
      record('cleanup: reset_demo_data() after officer demo-mode probe', cleanup.status === 200, `HTTP ${cleanup.status}, ${cleanup.text.slice(0, 160)}`)
    } else {
      console.log('\nSkipping officer-boundary checks — set SUPABASE_TEST_AS_OFFICER=1 after promoting the probe account to role=officer.')
    }
  } else {
    console.log('Skipping authenticated-role checks — no usable token (see above).')
  }

  console.log('\n--- Summary ---')
  const failed = results.filter((r) => !r.pass)
  console.log(`${results.length - failed.length}/${results.length} passed.`)
  if (failed.length) {
    console.log('Failures:')
    for (const f of failed) console.log(`  - ${f.name}: ${f.detail}`)
    process.exit(1)
  }
}

main().catch((e) => {
  console.error('Script error:', e)
  process.exit(1)
})
