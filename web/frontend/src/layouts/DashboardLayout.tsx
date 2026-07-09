import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/lib/auth'

const staffTabs = [
  { id: 'overview', label: 'Overview', icon: '🗺️' },
  { id: 'replay', label: 'Replay', icon: '⏪' },
  { id: 'network', label: 'Corridor', icon: '🕸️' },
  { id: 'learning', label: 'Learning', icon: '📈' },
  { id: 'fleet', label: 'Fleet', icon: '🔋' },
  { id: 'planner', label: 'Planner', icon: '📐' },
  { id: 'demo', label: 'Demo Mode', icon: '▶️' },
]

const adminOnlyTabs = [
  { id: 'officers', label: 'Officer Approvals', icon: '🛂' },
  { id: 'admin', label: 'Admin', icon: '⚙️' },
]

const mobileTabsStaff = [
  { id: 'overview', short: 'MAP', icon: '🗺️' },
  { id: 'replay', short: 'REPLAY', icon: '⏪' },
  { id: 'network', short: 'CORRIDOR', icon: '🕸️' },
  { id: 'fleet', short: 'FLEET', icon: '🔋' },
  { id: 'demo', short: 'DEMO', icon: '▶️' },
]

const mobileTabsAdmin = [
  { id: 'overview', short: 'MAP', icon: '🗺️' },
  { id: 'replay', short: 'REPLAY', icon: '⏪' },
  { id: 'demo', short: 'DEMO', icon: '▶️' },
  { id: 'fleet', short: 'FLEET', icon: '🔋' },
  { id: 'admin', short: 'ADMIN', icon: '⚙️' },
]

export function DashboardLayout() {
  const { profile, signOut } = useAuth()
  const isStaff = profile?.role === 'admin' || profile?.role === 'officer'
  const isAdmin = profile?.role === 'admin'

  const tabs = isStaff ? [...staffTabs, ...(isAdmin ? adminOnlyTabs : [])] : []
  const mobileTabs = isAdmin ? mobileTabsAdmin : mobileTabsStaff

  const userLabel = profile?.full_name ? `${profile.full_name} · ${profile.role.toUpperCase()}` : ''

  return (
    <div className="bg-brand-bg text-brand-fg flex min-h-screen flex-col">
      <header className="border-brand-fg/8 sticky top-0 z-50 flex h-14 items-center gap-3.5 border-b bg-[#0B0D0B] px-3 sm:px-6">
        <NavLink to="/" className="text-brand-fg flex items-center gap-2">
          <img src="/assets/logo.png" alt="EleTect logo" className="h-9.5 w-9.5 rounded-full object-cover" />
          <span className="font-sans text-[15px] font-semibold">EleTect Ops</span>
        </NavLink>
        <span className="text-brand-green border-brand-green/30 inline-flex items-center gap-1.5 rounded-full border bg-[rgba(95,169,124,0.1)] px-2.5 py-1 font-mono text-[10.5px] font-semibold tracking-widest">
          <span className="bg-brand-green h-1.5 w-1.5 animate-pulse rounded-full" />
          LIVE
        </span>
        <div className="ml-auto flex items-center gap-3">
          <span className="text-brand-fg/50 max-w-45 truncate font-mono text-[12.5px] font-medium">
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
                <span className="text-[15px]">{t.icon}</span>
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
          {mobileTabs.map((t) => (
            <NavLink
              key={t.id}
              to={`/dashboard/${t.id}`}
              className={({ isActive }) =>
                `flex min-h-12 min-w-14 flex-col items-center gap-0.5 rounded-xl px-2.5 py-2 ${
                  isActive ? 'text-brand-gold bg-[rgba(226,161,60,0.12)]' : 'text-brand-fg/55'
                }`
              }
            >
              <span className="text-[19px]">{t.icon}</span>
              <span className="font-mono text-[9.5px] font-semibold tracking-[0.04em]">{t.short}</span>
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}
