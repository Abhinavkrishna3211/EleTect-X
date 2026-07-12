// EleTect X — Day 5 seed data: a realistic profiles mix.
//
// schema.sql's profiles table is 1:1 with auth.users, so it cannot be seeded
// with plain INSERT statements the way nodes/events/health can — a profile
// needs a real auth user behind it, and the officer-request path specifically
// needs handle_new_user()'s trigger to fire from a real signup. This script
// uses the service-role Admin API to create a small, realistic set of
// pre-confirmed throwaway accounts (no confirmation email sent, so it doesn't
// touch Supabase Auth's rate-limited default sender), then promotes roles
// directly where schema.sql's own approval flow wouldn't apply (the approved
// officer below skips the queue on purpose — it exists to have at least one
// working officer login, not to test the approval flow itself; the pending
// one is what exercises the approval-queue screen).
//
// Idempotent: looks up each address by email first and skips creation if it
// already exists, so re-running after Day 3's leftover throwaway accounts (or
// a prior run of this script) is safe.
//
// The seed password is NOT hardcoded here, and must not be. These accounts live
// in the production project and one of them holds the `officer` role, which can
// read every staff table (nodes, events, health, maintenance). A password
// committed to a repo that is headed for public release with the contest
// submissions would be a working forest-officer login for anyone who reads it.
// It comes from the environment, and `.env.local` (gitignored) is where it
// lives locally — the same file scripts/qa-day5-responsive.mjs reads it from.
//
// Usage:
//   SUPABASE_URL=https://<ref>.supabase.co \
//   SUPABASE_SERVICE_ROLE_KEY=<service role key> \
//   QA_SEED_PASSWORD=<strong throwaway password> \
//     node scripts/seed-day5-profiles.mjs
//
// Re-running rotates the password on accounts that already exist, so this is
// also how you revoke a leaked one.

import { createClient } from '@supabase/supabase-js'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Same .env.local parse the QA scripts use, so the password only has to be set
// in one place.
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
const SEED_PASSWORD = process.env.QA_SEED_PASSWORD || envVars.QA_SEED_PASSWORD

if (!SUPABASE_URL || !SERVICE_ROLE_KEY) {
  console.error('Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables first.')
  process.exit(1)
}

if (!SEED_PASSWORD || SEED_PASSWORD.length < 16) {
  console.error('Set QA_SEED_PASSWORD (>= 16 chars) in the environment or web/frontend/.env.local.')
  console.error('One of these accounts holds the officer role — do not give it a guessable password.')
  process.exit(1)
}

const admin = createClient(SUPABASE_URL, SERVICE_ROLE_KEY, {
  auth: { autoRefreshToken: false, persistSession: false },
})

// Kothamangalam sector-7 area, close to the seeded node coordinates in
// seed-4b.sql, so proximity-alert logic has something realistic to work with.
const SECTOR_7_CENTRE = { lat: 10.058, lng: 76.628 }

async function findUserByEmail(email) {
  // Admin listUsers has no email filter in the JS SDK, so page through — the
  // seed set is tiny and this only runs a handful of times, not in a hot path.
  let page = 1
  for (;;) {
    const { data, error } = await admin.auth.admin.listUsers({ page, perPage: 200 })
    if (error) throw error
    const hit = data.users.find((u) => u.email === email)
    if (hit) return hit
    if (data.users.length < 200) return null
    page += 1
  }
}

async function ensureUser(email, metadata) {
  const existing = await findUserByEmail(email)
  if (existing) {
    // Reset the password rather than leaving whatever it was. This is what makes
    // a re-run a rotation: if a previous password leaked, running this again with
    // a new QA_SEED_PASSWORD revokes it.
    const { error } = await admin.auth.admin.updateUserById(existing.id, { password: SEED_PASSWORD })
    if (error) throw error
    console.log(`  exists: ${email} (${existing.id}) — password rotated`)
    return existing
  }
  const { data, error } = await admin.auth.admin.createUser({
    email,
    password: SEED_PASSWORD,
    email_confirm: true,
    user_metadata: metadata,
  })
  if (error) throw error
  console.log(`  created: ${email} (${data.user.id})`)
  return data.user
}

async function main() {
  console.log('--- pending officer request (drives the OfficerApprovals queue) ---')
  await ensureUser('officer.pending.seed@eletect-x.test', {
    full_name: 'Ravi Menon',
    phone: '+919812345601',
    officer_request: true,
    department: 'Kerala Forest Department',
    designation: 'Beat Forest Officer',
    official_email: 'officer.pending.seed@eletect-x.test',
  })

  console.log('--- approved officer (a working non-admin staff login) ---')
  const officer = await ensureUser('officer.approved.seed@eletect-x.test', {
    full_name: 'Deepa Nair',
    phone: '+919812345602',
  })
  {
    const { error } = await admin.from('profiles').update({ role: 'officer' }).eq('id', officer.id)
    if (error) throw error
    console.log('  role -> officer')
  }

  console.log('--- resident, alerts on, located in Sector 7 ---')
  const residentOn = await ensureUser('resident.alertson.seed@eletect-x.test', {
    full_name: 'Sunitha Joseph',
    phone: '+919812345603',
  })
  {
    const { error } = await admin
      .from('profiles')
      .update({
        alerts_enabled: true,
        lat: SECTOR_7_CENTRE.lat + 0.004,
        lng: SECTOR_7_CENTRE.lng - 0.006,
      })
      .eq('id', residentOn.id)
    if (error) throw error
    console.log('  alerts_enabled -> true, location set near Sector 7')
  }

  console.log('--- resident, alerts off, no location set (default/unengaged case) ---')
  await ensureUser('resident.alertsoff.seed@eletect-x.test', {
    full_name: 'Tomy Abraham',
    phone: '+919812345604',
  })

  console.log('\nDone. All four accounts now use the password in QA_SEED_PASSWORD.')
  console.log('(throwaway test accounts, not real users — but one holds the officer role,')
  console.log(' so delete them from Authentication → Users before the repo goes public.)')
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
