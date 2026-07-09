import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

interface OfficerRequest {
  id: number
  full_name: string
  department: string
  designation: string
  official_email: string
  phone: string | null
  status: 'pending' | 'approved' | 'rejected'
  created_at: string
}

export function OfficerApprovals() {
  const [requests, setRequests] = useState<OfficerRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [decidingId, setDecidingId] = useState<number | null>(null)

  async function load() {
    const { data } = await supabase
      .from('officer_requests')
      .select('*')
      .order('created_at', { ascending: false })
    setRequests((data as OfficerRequest[]) ?? [])
    setLoading(false)
  }

  useEffect(() => {
    supabase
      .from('officer_requests')
      .select('*')
      .order('created_at', { ascending: false })
      .then(({ data }) => {
        setRequests((data as OfficerRequest[]) ?? [])
        setLoading(false)
      })
  }, [])

  async function decide(id: number, action: 'approve' | 'reject') {
    setDecidingId(id)
    await supabase.rpc(action === 'approve' ? 'approve_officer_request' : 'reject_officer_request', {
      req_id: id,
    })
    await load()
    setDecidingId(null)
  }

  const pendingCount = requests.filter((r) => r.status === 'pending').length

  return (
    <div className="flex max-w-225 flex-col gap-4">
      <div className="flex flex-wrap items-baseline gap-3.5">
        <h1 className="m-0 font-serif text-[clamp(24px,3.5vw,32px)] font-normal">Officer approval queue</h1>
        <span className="text-brand-gold font-mono text-[12.5px] font-semibold">
          {pendingCount} SUBMITTED
        </span>
      </div>
      <p className="text-brand-fg/65 m-0 max-w-[70ch] font-sans text-[14.5px] leading-relaxed">
        Officers who sign up submit their department, designation, and official email. Review each request and
        approve only verified Forest Department staff.
      </p>

      <div className="flex flex-col gap-3">
        {loading && <p className="text-brand-fg/40 font-mono text-xs">Loading…</p>}
        {!loading && requests.length === 0 && (
          <p className="text-brand-fg/40 font-mono text-xs">No officer requests yet.</p>
        )}
        {requests.map((r) => (
          <div
            key={r.id}
            className="border-brand-fg/10 flex flex-wrap items-center gap-4 rounded-2xl border bg-[#0B0D0B] px-5.5 py-5"
          >
            <div
              className="grid h-11 w-11 shrink-0 place-items-center rounded-full text-[15px] font-semibold"
              style={{ background: 'linear-gradient(140deg,#2F5E3F,#0F1D14)', color: '#E2A13C' }}
            >
              🛂
            </div>
            <div className="min-w-55 flex-1">
              <p className="m-0 mb-0.5 font-sans text-[15px] font-semibold">
                {r.full_name}{' '}
                <span
                  className={`ml-1.5 rounded-full border px-2.25 py-0.5 font-mono text-[11px] font-semibold ${
                    r.status === 'approved'
                      ? 'border-brand-green text-brand-green'
                      : r.status === 'rejected'
                        ? 'border-brand-red text-brand-red'
                        : 'border-brand-yellow text-brand-yellow'
                  }`}
                >
                  {r.status.toUpperCase()}
                </span>
              </p>
              <p className="text-brand-fg/65 m-0 mb-0.5 font-sans text-[13px] font-medium">
                {r.designation} · {r.department}
              </p>
              <p className="text-brand-fg/45 m-0 font-mono text-xs font-medium">
                {r.official_email} · {r.phone ?? '–'} · submitted{' '}
                {new Date(r.created_at).toLocaleDateString()}
              </p>
            </div>
            {r.status !== 'pending' ? (
              <span className="text-brand-fg/40 font-sans text-[13px] font-semibold">Decision recorded</span>
            ) : (
              <div className="flex gap-2">
                <button
                  onClick={() => decide(r.id, 'approve')}
                  disabled={decidingId === r.id}
                  className="text-brand-green min-h-10 rounded-full border px-4 py-2.25 font-sans text-[13px] font-semibold transition-colors disabled:opacity-60"
                  style={{ background: 'rgba(95,169,124,0.15)', borderColor: 'rgba(95,169,124,0.5)' }}
                >
                  Approve
                </button>
                <button
                  onClick={() => decide(r.id, 'reject')}
                  disabled={decidingId === r.id}
                  className="text-brand-red min-h-10 rounded-full border px-4 py-2.25 font-sans text-[13px] font-semibold transition-colors disabled:opacity-60"
                  style={{ background: 'rgba(226,91,74,0.12)', borderColor: 'rgba(226,91,74,0.45)' }}
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
