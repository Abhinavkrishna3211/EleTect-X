import { useEffect, useRef, useState } from 'react'
import {
  BatteryCharging,
  History,
  Map as MapIcon,
  MoreHorizontal,
  Network,
  PlayCircle,
  Ruler,
  TrendingUp,
  UserCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/lib/auth'

// One source of truth for both navs. The mobile bar used to carry its own
// hand-written tab arrays, which silently drifted: an admin on a phone had no
// way to reach the officer-approval queue at all, and neither staff role could
// reach Learning or Planner. Anything added here now appears at every
// breakpoint — the bottom bar spills the overflow into a sheet rather than
// truncating it away.
interface Tab {
  id: string
  label: string
  short: string
  icon: LucideIcon
}

const staffTabs: Tab[] = [
  { id: 'overview', label: 'Overview', short: 'MAP', icon: MapIcon },
  { id: 'replay', label: 'Replay', short: 'REPLAY', icon: History },
  { id: 'network', label: 'Corridor', short: 'CORRIDOR', icon: Network },
  { id: 'learning', label: 'Learning', short: 'LEARNING', icon: TrendingUp },
  { id: 'fleet', label: 'Fleet', short: 'FLEET', icon: BatteryCharging },
  { id: 'planner', label: 'Planner', short: 'PLANNER', icon: Ruler },
  { id: 'demo', label: 'Demo Mode', short: 'DEMO', icon: PlayCircle },
]

const adminOnlyTabs: Tab[] = [
  { id: 'officers', label: 'Officer Approvals', short: 'OFFICERS', icon: UserCheck },
  { id: 'admin', label: 'Admin', short: 'ADMIN', icon: Users },
]

// Four fit across a 390px viewport alongside the More button without crowding
// the 44px minimum tap target.
const MOBILE_BAR_SLOTS = 4

const mobileLinkClass = (isActive: boolean) =>
  `flex min-h-12 min-w-14 flex-col items-center gap-0.5 rounded-xl px-2.5 py-2 ${
    isActive ? 'text-brand-gold bg-[rgba(226,161,60,0.12)]' : 'text-brand-fg/55'
  }`

function MoreSheet({ tabs, onClose }: { tabs: Tab[]; onClose: () => void }) {
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKeyDown)
    // Move focus into the sheet so keyboard and screen-reader users land inside
    // it rather than continuing through the page behind the overlay.
    panelRef.current?.querySelector('a')?.focus()
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-60 bg-black/60 md:hidden"
      onClick={onClose}
      role="button"
      tabIndex={-1}
      aria-label="Close menu"
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label="More sections"
        onClick={(e) => e.stopPropagation()}
        className="border-brand-fg/10 absolute right-0 bottom-0 left-0 flex flex-col gap-1 rounded-t-2xl border-t bg-[#090C0A] p-3 pb-6"
      >
        <span className="text-brand-fg/40 px-2 pt-1 pb-2 font-mono text-[10.5px] font-semibold tracking-[0.12em]">
          MORE SECTIONS
        </span>
        {tabs.map((t) => (
          <NavLink
            key={t.id}
            to={`/dashboard/${t.id}`}
            onClick={onClose}
            className={({ isActive }) =>
              `flex min-h-12 items-center gap-3 rounded-xl px-3 py-2.5 font-sans text-[14px] font-semibold ${
                isActive ? 'text-brand-gold bg-[rgba(226,161,60,0.12)]' : 'text-brand-fg/70'
              }`
            }
          >
            <t.icon size={18} strokeWidth={1.75} aria-hidden />
            {t.label}
          </NavLink>
        ))}
      </div>
    </div>
  )
}

export function DashboardLayout() {
  const { profile, signOut } = useAuth()
  const { pathname } = useLocation()
  const [moreOpen, setMoreOpen] = useState(false)
  const [sheetPath, setSheetPath] = useState(pathname)

  const isStaff = profile?.role === 'admin' || profile?.role === 'officer'
  const isAdmin = profile?.role === 'admin'

  const tabs = isStaff ? [...staffTabs, ...(isAdmin ? adminOnlyTabs : [])] : []
  const barTabs = tabs.slice(0, MOBILE_BAR_SLOTS)
  const overflowTabs = tabs.slice(MOBILE_BAR_SLOTS)

  // Close the sheet whenever the route changes. Its own links already close it
  // on tap; this covers browser back/forward, which would otherwise leave the
  // sheet hanging over the new route. Adjusted during render rather than in an
  // effect — the effect version cascades an extra render on every navigation.
  if (sheetPath !== pathname) {
    setSheetPath(pathname)
    setMoreOpen(false)
  }

  const overflowActive = overflowTabs.some((t) => pathname === `/dashboard/${t.id}`)
  const userLabel = profile?.full_name ? `${profile.full_name} · ${profile.role.toUpperCase()}` : ''

  return (
    <div className="bg-brand-bg text-brand-fg flex min-h-screen flex-col">
      <header className="border-brand-fg/8 sticky top-0 z-50 flex h-14 items-center gap-3.5 border-b bg-[#0B0D0B] px-3 sm:px-6">
        <NavLink to="/" className="text-brand-fg flex shrink-0 items-center gap-2">
          <img src="/assets/logo.png" alt="EleTect logo" className="h-9.5 w-9.5 rounded-full object-cover" />
          <span className="font-sans text-[15px] font-semibold">EleTect Ops</span>
        </NavLink>
        <span className="text-brand-green border-brand-green/30 inline-flex shrink-0 items-center gap-1.5 rounded-full border bg-[rgba(95,169,124,0.1)] px-2.5 py-1 font-mono text-[10.5px] font-semibold tracking-widest">
          <span className="bg-brand-green h-1.5 w-1.5 animate-pulse rounded-full" />
          LIVE
        </span>
        {/* min-w-0 on both the group and the label is what actually lets
            `truncate` engage. Without it a flex item refuses to shrink below its
            content width, so a long "Full Name · OFFICER" pushed the Sign out
            button past the right edge and scrolled the whole dashboard
            sideways on a phone. */}
        <div className="ml-auto flex min-w-0 items-center gap-3">
          <span className="text-brand-fg/50 min-w-0 truncate font-mono text-[12.5px] font-medium">
            {userLabel}
          </span>
          <button
            onClick={signOut}
            className="border-brand-fg/20 text-brand-fg/75 hover:border-brand-fg hover:text-brand-fg min-h-9.5 shrink-0 rounded-full border px-3.5 py-2 font-sans text-[12.5px] font-semibold whitespace-nowrap transition-colors"
          >
            Sign out
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {isStaff && (
          <nav className="border-brand-fg/7 hidden w-50 shrink-0 flex-col gap-0.75 border-r bg-[#090C0A] p-2.5 md:flex">
            {tabs.map((t) => (
              <NavLink
                key={t.id}
                to={`/dashboard/${t.id}`}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-[10px] px-3.5 py-2.75 font-sans text-[13.5px] font-semibold transition-colors ${
                    isActive ? 'text-brand-gold bg-[rgba(226,161,60,0.1)]' : 'text-brand-fg/60 hover:text-brand-fg'
                  }`
                }
              >
                <t.icon size={17} strokeWidth={1.75} aria-hidden />
                {t.label}
              </NavLink>
            ))}
          </nav>
        )}

        <div className="min-w-0 flex-1 overflow-y-auto p-3.5 pb-24 sm:p-7">
          <Outlet />
        </div>
      </div>

      {isStaff && (
        <nav className="border-brand-fg/10 fixed right-0 bottom-0 left-0 z-55 flex justify-around border-t bg-[rgba(9,12,10,0.96)] px-1 py-1.5 backdrop-blur-md md:hidden">
          {barTabs.map((t) => (
            <NavLink key={t.id} to={`/dashboard/${t.id}`} className={({ isActive }) => mobileLinkClass(isActive)}>
              <t.icon size={20} strokeWidth={1.75} aria-hidden />
              <span className="font-mono text-[9.5px] font-semibold tracking-[0.04em]">{t.short}</span>
            </NavLink>
          ))}

          {overflowTabs.length > 0 && (
            <button
              onClick={() => setMoreOpen((v) => !v)}
              aria-expanded={moreOpen}
              aria-haspopup="dialog"
              className={mobileLinkClass(moreOpen || overflowActive)}
            >
              <MoreHorizontal size={20} strokeWidth={1.75} aria-hidden />
              <span className="font-mono text-[9.5px] font-semibold tracking-[0.04em]">MORE</span>
            </button>
          )}
        </nav>
      )}

      {moreOpen && overflowTabs.length > 0 && (
        <MoreSheet tabs={overflowTabs} onClose={() => setMoreOpen(false)} />
      )}
    </div>
  )
}
