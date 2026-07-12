// EleTect X — contest-judge demo accounts.
//
// Judges need a working login to evaluate the dashboard, but the login page must
// not advertise one: a public page that names an account hands a visitor half a
// credential pair for free (which is exactly why the demo-account list was removed
// from Login.tsx). So the accounts are created here and the credentials are written
// to docs/internal/judge-demo-credentials.md — a git-ignored file — for you to send
// to judges directly.
//
// Same shape as scripts/seed-day5-profiles.mjs: `profiles` is 1:1 with auth.users,
// so it cannot be seeded with plain INSERTs; these go through the service-role Admin
// API as pre-confirmed users (email_confirm: true, so Supabase Auth's rate-limited
// default sender is never touched), then the role is promoted directly.
//
// The password is NOT hardcoded and must not be. One of these accounts holds the
// **admin** role on the production project — it can approve officers and write node
// state. It comes from the environment; .env.local (git-ignored) is where it lives.
// Re-running rotates the password on accounts that already exist, so a leaked one
// can be revoked by re-running with a new value.
//
// Usage:
//   SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... QA_JUDGE_PASSWORD=... \
//     node scripts/seed-judge-accounts.mjs
//
// DELETE THESE ACCOUNTS once the judging window closes — see the generated file.

import { createClient } from '@supabase/supabase-js'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..', '..', '..')

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

const SUPABASE_URL = process.env.SUPABASE_URL
const SERVICE_ROLE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY
const JUDGE_PASSWORD = process.env.QA_JUDGE_PASSWORD || envVars.QA_JUDGE_PASSWORD

if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
  console.error('Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY first.')
  process.exit(1)
}
if (!JUDGE_PASSWORD || JUDGE_PASSWORD.length < 16) {
  console.error('Set QA_JUDGE_PASSWORD (>= 16 chars) in the environment or web/frontend/.env.local.')
  console.error('One of these accounts is an ADMIN on the production project — no guessable password.')
  process.exit(1)
}

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
})

// Same sector as the seeded field data, so the resident view has real activity.
const SECTOR_7_CENTRE = { lat: 10.058, lng: 76.628 }

const ACCOUNTS = [
  {
    email: 'judge.admin@eletect-x.test',
    role: 'admin',
    metadata: { full_name: 'Contest Judge (Admin)' },
    note: 'Full staff dashboard: live map, replay, corridor, learning, fleet, planner, Demo Mode, officer approvals.',
  },
  {
    email: 'judge.resident@eletect-x.test',
    role: 'public',
    metadata: { full_name: 'Contest Judge (Resident)' },
    note: 'Resident view: area risk derived from public_area_risk, recent activity counts, alerts opt-in toggle.',
  },
]

async function findUserByEmail(email) {
  for (let page = 1; ; page++) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 200 })
    if (error) throw error
    const hit = data.users.find((u) => u.email === email)
    if (hit) return hit
    if (data.users.length < 200) return null
  }
}

async function ensureUser({ email, metadata }) {
  const existing = await findUserByEmail(email)
  if (existing) {
    const { error } = await admin.auth.admin.updateUserById(existing.id, { password: JUDGE_PASSWORD })
    if (error) throw error
    console.log(`  exists: ${email} — password rotated`)
    return existing
  }
  const { data, error } = await admin.auth.admin.createUser({
    email,
    password: JUDGE_PASSWORD,
    email_confirm: true,
    user_metadata: metadata,
  })
  if (error) throw error
  console.log(`  created: ${email}`)
  return data.user
}

async function main() {
  for (const acct of ACCOUNTS) {
    const user = await ensureUser(acct)

    const patch = { role: acct.role }
    if (acct.role === 'public') {
      // Give the resident judge a location + alerts on, so their view is populated
      // rather than an empty state.
      patch.alerts_enabled = true
      patch.lat = SECTOR_7_CENTRE.lat + 0.004
      patch.lng = SECTOR_7_CENTRE.lng - 0.006
    }
    const { error } = await admin.from('profiles').update(patch).eq('id', user.id)
    if (error) throw error
    console.log(`  role -> ${acct.role}`)
  }

  // Verify against a fresh read rather than trusting the writes above.
  console.log('\n--- verifying ---')
  for (const acct of ACCOUNTS) {
    const u = await findUserByEmail(acct.email)
    const { data: p } = await admin.from('profiles').select('role').eq('id', u.id).single()
    const ok = p?.role === acct.role
    console.log(`  ${ok ? 'ok:  ' : 'FAIL:'} ${acct.email} role=${p?.role} (expected ${acct.role})`)
    if (!ok) process.exit(1)
  }

  const outDir = path.join(repoRoot, 'docs', 'internal')
  fs.mkdirSync(outDir, { recursive: true })
  const outFile = path.join(outDir, 'judge-demo-credentials.md')
  const today = new Date().toISOString().slice(0, 10)

  const body = `# Contest judge demo credentials (LOCAL ONLY — git-ignored)

Generated ${today} by \`web/frontend/scripts/seed-judge-accounts.mjs\`.

**Do not commit this file, do not put these on the site, do not put them in a
submission page that is publicly readable.** \`docs/internal/\` is git-ignored via
\`.git/info/exclude\`. Send them to judges directly (email / submission portal's
private notes field).

Live app: <https://eletect.vercel.app>

| Role | Email | Password |
|---|---|---|
${ACCOUNTS.map((a) => `| ${a.role} | \`${a.email}\` | \`${JUDGE_PASSWORD}\` |`).join('\n')}

${ACCOUNTS.map((a) => `- **${a.email}** — ${a.note}`).join('\n')}

## Rotate or delete when judging closes

\`judge.admin@eletect-x.test\` holds the **admin** role on the *production* Supabase
project: it can approve officer requests and mutate node state. It is a throwaway on
the \`.test\` domain, but it is real, and it must not outlive the contest.

- **Rotate:** set a new \`QA_JUDGE_PASSWORD\` in \`web/frontend/.env.local\` and re-run
  the script — it resets the password on the existing accounts.
- **Delete:** remove both from Supabase → Authentication → Users. \`profiles\` cascades
  off \`auth.users\`, so the profile rows go with them.

Deadlines for reference: Robu submission 23 Aug 2026 · Hackster submission 30 Aug 2026.
Delete once both judging windows have closed.
`

  fs.writeFileSync(outFile, body, 'utf8')
  console.log(`\nCredentials written to docs/internal/judge-demo-credentials.md (git-ignored).`)
  console.log('Send them to judges from there. Delete the accounts when judging closes.')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
