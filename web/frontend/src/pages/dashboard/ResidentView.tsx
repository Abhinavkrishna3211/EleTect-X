import { useState } from 'react'
import { useAuth } from '@/lib/auth'
import { supabase } from '@/lib/supabase'

const recentAlerts = [
  {
    icon: '🐘',
    title: 'Elephants moved back to forest: all clear',
    meta: 'Yesterday 22:10 · 2 km NE of Kothamangalam',
  },
  {
    icon: '⚠️',
    title: 'Elephant herd detected: stay indoors, avoid NE paddy road',
    meta: 'Yesterday 21:47 · alert sent by SMS',
  },
  {
    icon: '🐗',
    title: 'Wild boar deterred near farm boundary: no action needed',
    meta: 'Tue 19:12 · 1 km S',
  },
]

export function ResidentView() {
  const { profile, refreshProfile } = useAuth()
  const [saving, setSaving] = useState(false)
  const smsOn = profile?.alerts_enabled ?? false

  async function toggleSms() {
    if (!profile) return
    setSaving(true)
    await supabase.from('profiles').update({ alerts_enabled: !smsOn }).eq('id', profile.id)
    await refreshProfile()
    setSaving(false)
  }

  return (
    <div className="mx-auto flex max-w-170 flex-col gap-4">
      <h1 className="m-0 mt-2 font-serif text-[clamp(26px,4vw,36px)] font-normal">Your area tonight</h1>

      <div className="border-brand-green/35 flex flex-wrap items-center gap-4.5 rounded-[18px] border bg-[rgba(95,169,124,0.07)] p-6.5">
        <div className="border-brand-green grid h-14 w-14 place-items-center rounded-full border-2 text-2xl">
          🟢
        </div>
        <div className="min-w-50 flex-1">
          <p className="text-brand-fg/50 m-0 mb-1 font-mono text-[11.5px] font-semibold tracking-[0.12em]">
            KOTHAMANGALAM SECTOR · RISK LEVEL
          </p>
          <p className="text-brand-green m-0 font-sans text-xl font-semibold">Low: no wildlife near villages</p>
        </div>
      </div>

      <div className="border-brand-fg/10 rounded-[18px] border bg-[#0B0D0B] p-6">
        <h2 className="m-0 mb-4 font-sans text-base font-semibold">Recent alerts near you</h2>
        <div className="flex flex-col gap-3">
          {recentAlerts.map((a, i) => (
            <div
              key={a.title}
              className={`flex items-start gap-3 ${
                i < recentAlerts.length - 1 ? 'border-brand-fg/6 border-b pb-3' : ''
              }`}
            >
              <span className="text-lg">{a.icon}</span>
              <div className="flex-1">
                <p className="m-0 font-sans text-sm font-semibold">{a.title}</p>
                <p className="text-brand-fg/45 m-0.5 mt-0.5 font-mono text-[12.5px]">{a.meta}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-brand-fg/10 rounded-[18px] border bg-[#0B0D0B] p-6">
        <button
          onClick={toggleSms}
          disabled={saving}
          className="flex min-h-11 w-full items-center justify-between gap-3.5 bg-transparent p-0 disabled:opacity-60"
        >
          <span className="text-left">
            <span className="block font-sans text-[15px] font-semibold">SMS alerts</span>
            <span className="text-brand-fg/50 mt-0.5 block font-sans text-[13px]">
              {smsOn ? 'On · you will get SMS alerts for your area' : 'Off · turn on to receive SMS alerts'}
            </span>
          </span>
          <span
            className={`relative h-7 w-12.5 shrink-0 rounded-full transition-colors ${
              smsOn ? 'bg-brand-green' : 'bg-brand-fg/15'
            }`}
          >
            <span
              className={`bg-brand-fg absolute top-0.75 h-5.5 w-5.5 rounded-full transition-all ${
                smsOn ? 'left-6.5' : 'left-0.75'
              }`}
            />
          </span>
        </button>
      </div>

      <p className="text-brand-fg/40 m-0 font-sans text-[12.5px] leading-relaxed">
        Emergency? Call the Forest Department control room: 1926. This dashboard shows safety information only.
      </p>
    </div>
  )
}
