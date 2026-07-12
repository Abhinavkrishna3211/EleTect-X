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
export function useAlertsOptIn() {
  const { profile, refreshProfile } = useAuth()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const signedIn = profile != null
  const enabled = profile?.alerts_enabled ?? false

  async function setEnabled(next: boolean) {
    if (!profile || saving) return
    setSaving(true)
    setError(null)
    const { error: updateError } = await supabase
      .from('profiles')
      .update({ alerts_enabled: next })
      .eq('id', profile.id)
    if (updateError) {
      // Surface it. Silently swallowing this leaves the switch showing a
      // promise the backend never recorded — the resident believes they are
      // covered and is not.
      setError('Could not save that. Check your connection and try again.')
    } else {
      await refreshProfile()
    }
    setSaving(false)
  }

  return { signedIn, enabled, saving, error, setEnabled }
}
