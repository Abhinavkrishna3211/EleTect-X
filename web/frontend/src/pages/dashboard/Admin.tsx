import { useCallback, useEffect, useState } from 'react'
import { Loader2, ShieldCheck, UserMinus, UserPlus } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import type { Role } from '@/lib/auth'

// User + role management. Deliberately NOT firmware/OTA: no real firmware pipeline
// exists on device/mcu yet, and a mocked OTA panel would undercut the credibility
// the rest of this system is built on. That screen lands when the firmware does.
//
// Every action here is authorised server-side by is_admin() inside the RPC — see
// migrations/0003. This page hiding a button is a convenience, not the control: a
// non-admin calling admin_set_role() directly with their own JWT is rejected by the
// database, and admin_list_users() returns them zero rows.

interface AdminUser {
  id: string
  email: string
  role: Role
  full_name: string | null
  created_at: string
  deactivated: boolean
  is_self: boolean
}

const ROLES: Role[] = ['public', 'officer', 'admin']

const ROLE_STYLE: Record<Role, string> = {
  admin: 'text-brand-gold border-brand-gold/35 bg-[rgba(226,161,60,0.1)]',
  officer: 'text-brand-green border-brand-green/35 bg-[rgba(95,169,124,0.1)]',
  public: 'text-brand-fg/60 border-brand-fg/15 bg-brand-fg/5',
}

export function Admin() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    const { data, error: err } = await supabase.rpc('admin_list_users')
    if (err) {
      setError(err.message)
      setUsers([])
    } else {
      setUsers((data ?? []) as AdminUser[])
    }
    setLoading(false)
  }, [])

  // Subscribe-style fetch rather than calling load() in the effect body: the latter
  // trips react-hooks/set-state-in-effect and cascades an extra render.
  useEffect(() => {
    let cancelled = false
    supabase
      .rpc('admin_list_users')
      .then(({ data, error: err }) => {
        if (cancelled) return
        if (err) {
          setError(err.message)
          setUsers([])
        } else {
          setUsers((data ?? []) as AdminUser[])
        }
        setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // Both mutations funnel through here so the busy/error/refetch handling exists once.
  async function run(id: string, fn: string, args: Record<string, unknown>) {
    setBusyId(id)
    setError(null)
    const { error: err } = await supabase.rpc(fn, args)
    // Surface the database's own message: the guards return real reasons
    // ("cannot demote the last remaining admin"), which are worth showing verbatim
    // rather than flattening to "something went wrong".
    if (err) setError(err.message)
    await load()
    setBusyId(null)
  }

  const adminCount = users.filter((u) => u.role === 'admin' && !u.deactivated).length

  return (
    <div className="flex max-w-[1000px] flex-col gap-4">
      <div>
        <h1 className="m-0 mb-1.5 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Administration</h1>
        <p className="text-brand-fg/60 m-0 max-w-[70ch] font-sans text-sm leading-relaxed">
          Manage who can sign in and what they can see. Role changes take effect on the user's next
          request; deactivating an account blocks sign-in immediately, at the auth layer.
        </p>
      </div>

      {error && (
        <div className="border-brand-red/40 rounded-xl border bg-[rgba(226,91,74,0.08)] px-4 py-3">
          <p className="text-brand-red m-0 font-sans text-[13.5px] font-medium">{error}</p>
        </div>
      )}

      <div className="border-brand-fg/10 overflow-hidden rounded-2xl border bg-[#0B0D0B]">
        <div className="border-brand-fg/8 flex items-center justify-between border-b px-4.5 py-3.5">
          <h2 className="m-0 font-sans text-sm font-semibold">Users</h2>
          <span className="text-brand-fg/45 font-mono text-[11px] font-semibold tracking-[0.08em]">
            {loading ? 'LOADING…' : `${users.length} TOTAL · ${adminCount} ADMIN`}
          </span>
        </div>

        {loading ? (
          <p className="text-brand-fg/40 m-0 px-4.5 py-8 text-center font-mono text-[12px]">Loading users…</p>
        ) : users.length === 0 ? (
          <p className="text-brand-fg/40 m-0 px-4.5 py-8 text-center font-mono text-[12px]">
            No users visible. (This screen is admin-only — the server returns nothing to anyone else.)
          </p>
        ) : (
          <div className="flex flex-col">
            {users.map((u) => {
              const busy = busyId === u.id
              return (
                <div
                  key={u.id}
                  className="border-brand-fg/5 flex flex-wrap items-center gap-3 border-b px-4.5 py-3.5 last:border-b-0"
                >
                  <div className="min-w-50 flex-1">
                    <p className="m-0 flex items-center gap-2 font-sans text-[14px] font-semibold">
                      <span className="truncate">{u.full_name || u.email}</span>
                      {u.is_self && (
                        <span className="text-brand-fg/45 font-mono text-[10px] font-semibold tracking-[0.08em]">
                          YOU
                        </span>
                      )}
                      {u.deactivated && (
                        <span className="text-brand-red border-brand-red/35 rounded-full border bg-[rgba(226,91,74,0.1)] px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.06em]">
                          DEACTIVATED
                        </span>
                      )}
                    </p>
                    <p className="text-brand-fg/45 m-0 mt-0.5 truncate font-mono text-[12px]">{u.email}</p>
                  </div>

                  <span
                    className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 font-mono text-[10.5px] font-semibold tracking-[0.08em] ${ROLE_STYLE[u.role]}`}
                  >
                    {u.role === 'admin' && <ShieldCheck size={12} strokeWidth={2} aria-hidden />}
                    {u.role.toUpperCase()}
                  </span>

                  <div className="flex shrink-0 items-center gap-2">
                    <label className="sr-only" htmlFor={`role-${u.id}`}>
                      Role for {u.email}
                    </label>
                    <select
                      id={`role-${u.id}`}
                      value={u.role}
                      disabled={u.is_self || busy}
                      onChange={(e) => run(u.id, 'admin_set_role', { p_user: u.id, p_role: e.target.value })}
                      className="border-brand-fg/15 text-brand-fg min-h-9 rounded-lg border bg-[#0F1D14] px-2.5 py-1.5 font-sans text-[13px] disabled:cursor-not-allowed disabled:opacity-45"
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                    </select>

                    <button
                      type="button"
                      disabled={u.is_self || busy}
                      onClick={() =>
                        run(u.id, 'admin_set_deactivated', { p_user: u.id, p_deactivated: !u.deactivated })
                      }
                      className={`inline-flex min-h-9 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 font-sans text-[13px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${
                        u.deactivated
                          ? 'border-brand-green/35 text-brand-green hover:bg-brand-green/10'
                          : 'border-brand-red/35 text-brand-red hover:bg-brand-red/10'
                      }`}
                    >
                      {busy ? (
                        <Loader2 size={14} className="animate-spin" aria-hidden />
                      ) : u.deactivated ? (
                        <UserPlus size={14} strokeWidth={2} aria-hidden />
                      ) : (
                        <UserMinus size={14} strokeWidth={2} aria-hidden />
                      )}
                      {u.deactivated ? 'Reactivate' : 'Deactivate'}
                    </button>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>

      <p className="text-brand-fg/40 m-0 font-sans text-[12.5px] leading-relaxed">
        You cannot change your own role or deactivate your own account, and the last remaining admin
        cannot be demoted or deactivated — both rules are enforced by the database, not this page.
        Firmware / OTA management is not here yet: it lands when the device pipeline is real, not before.
      </p>
    </div>
  )
}
