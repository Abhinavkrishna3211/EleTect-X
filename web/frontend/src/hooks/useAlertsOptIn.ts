import { useState } from 'react'
import { useAuth } from '@/lib/auth'
import { supabase } from '@/lib/supabase'

// The single opt-in write. `profiles.alerts_enabled` is the one flag send-alert
// fans out on, so both places a resident can opt in — the Stay Safe page and the
// resident dashboard toggle — go through this rather than each carrying its own
// copy of the update.
//
// There is deliberately no anonymous opt-in path and no separate consent table:
// a resident opts in by holding an account, and the signup + email confirmation
// flow is the consent record. A visitor who is not signed in is sent to /signup
// instead of being asked for a phone number the app has nowhere to put.
//
// The location write lives here too, because the flag alone does not reach
// anyone. send-alert selects opted-in residents and then filters them on
// `p.lat != null` before measuring the 3 km radius, so a resident with the flag
// set and no position is dropped silently - the toggle reads "On" and no alert
// will ever be sent. Keeping both writes behind one hook is what lets every
// caller see `located` beside `enabled` and say so.
export function useAlertsOptIn() {
  const { profile, refreshProfile } = useAuth()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const signedIn = profile != null
  const enabled = profile?.alerts_enabled ?? false
  // Alerts on with no location is the state the UI used to describe as full
  // coverage; every caller of this hook has to be able to tell the two apart.
  const located = profile?.lat != null && profile?.lng != null

  async function write(patch: Record<string, unknown>, failure: string) {
    if (!profile || saving) return false
    setSaving(true)
    setError(null)
    const { error: updateError } = await supabase.from('profiles').update(patch).eq('id', profile.id)
    if (updateError) {
      // Surface it. Silently swallowing this leaves the switch showing a
      // promise the backend never recorded — the resident believes they are
      // covered and is not.
      setError(failure)
      setSaving(false)
      return false
    }
    await refreshProfile()
    setSaving(false)
    return true
  }

  async function setEnabled(next: boolean) {
    await write({ alerts_enabled: next }, 'Could not save that. Check your connection and try again.')
  }

  // Stored at the precision the browser gave us. Rounding a home position to
  // protect privacy would be a false comfort - the row is readable by staff
  // either way (profiles' p_staff_read) - and it would blur the only input the
  // 3 km match has.
  async function setLocation(lat: number, lng: number) {
    return write({ lat, lng }, 'Could not save your location. Check your connection and try again.')
  }

  async function clearLocation() {
    return write({ lat: null, lng: null }, 'Could not remove your location. Try again.')
  }

  return { signedIn, enabled, located, saving, error, setEnabled, setLocation, clearLocation }
}
