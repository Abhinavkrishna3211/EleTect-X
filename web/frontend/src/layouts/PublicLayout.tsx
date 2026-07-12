import { useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { navLinks } from '@/lib/content'
import { useScrollReveal } from '@/hooks/useScrollReveal'

export function PublicLayout() {
  const [navOpen, setNavOpen] = useState(false)
  const location = useLocation()
  useScrollReveal()

  return (
    <div className="bg-brand-bg text-brand-fg min-h-screen">
      <header className="border-brand-fg/7 bg-brand-bg/72 fixed inset-x-0 top-0 z-50 border-b backdrop-blur-md">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <Link to="/" className="text-brand-fg flex items-center gap-2.5" onClick={() => setNavOpen(false)}>
            <img src="/assets/logo.png" alt="EleTect logo" className="h-10.75 w-10.75 rounded-full object-cover" />
            <span className="font-sans text-[17px] font-semibold tracking-wide">EleTect</span>
          </Link>

          <nav className="hidden items-center gap-5 md:flex lg:gap-7">
            {navLinks.map((l) => (
              <NavLink
                key={l.href}
                to={l.href}
                end={l.href === '/'}
                className={({ isActive }) =>
                  `font-sans text-[13.5px] font-medium tracking-wide transition-colors ${
                    isActive
                      ? 'text-brand-gold'
                      : 'text-brand-fg/70 hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
            <Link
              to="/dashboard"
              className="bg-brand-gold hover:bg-brand-gold-hover rounded-full px-4.5 py-2.25 font-sans text-[13px] font-semibold tracking-wide text-[#0B140E]"
            >
              Dashboard
            </Link>
          </nav>

          <button
            onClick={() => setNavOpen((v) => !v)}
            aria-label="Menu"
            className="border-brand-fg/20 text-brand-fg min-h-11 rounded-[10px] border px-3.5 py-2.5 font-sans text-[13px] font-semibold md:hidden"
          >
            {navOpen ? '✕ Close' : '☰ Menu'}
          </button>
        </div>

        {navOpen && (
          <nav className="bg-brand-bg/97 flex flex-col gap-0.5 px-5 pt-2 pb-5 md:hidden">
            {navLinks.map((l) => (
              <NavLink
                key={l.href}
                to={l.href}
                end={l.href === '/'}
                onClick={() => setNavOpen(false)}
                className={({ isActive }) =>
                  `border-brand-fg/6 border-b py-3.5 font-sans text-base font-medium ${
                    isActive ? 'text-brand-gold' : 'text-brand-fg/70'
                  }`
                }
              >
                {l.label}
              </NavLink>
            ))}
            <Link
              to="/dashboard"
              onClick={() => setNavOpen(false)}
              className="bg-brand-gold mt-3.5 rounded-xl p-3.5 text-center font-sans text-[15px] font-semibold text-[#0B140E]"
            >
              Dashboard login
            </Link>
          </nav>
        )}
      </header>

      <main key={location.pathname} className="flex-1">
        <Outlet />
      </main>

      <footer className="border-brand-fg/7 bg-[#060A08]">
        <div className="mx-auto flex max-w-6xl flex-wrap justify-between gap-7 px-4 py-12 sm:px-6 lg:px-8">
          <div className="max-w-80">
            <div className="mb-3.5 flex items-center gap-2.5">
              <img src="/assets/logo.png" alt="EleTect logo" className="h-9.5 w-9.5 rounded-full object-cover" />
              <span className="font-sans text-base font-semibold">EleTect</span>
            </div>
            <p className="text-brand-fg/50 font-sans text-[13.5px] leading-relaxed">
              Protecting farms, forests, and the future.
            </p>
          </div>

          <nav className="flex flex-wrap gap-10 sm:gap-16">
            <div className="flex flex-col gap-2.5">
              <span className="text-brand-fg/40 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                PLATFORM
              </span>
              <Link to="/technology" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Technology
              </Link>
              <Link to="/solutions" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Solutions
              </Link>
              <Link to="/deployments" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Deployments
              </Link>
            </div>
            <div className="flex flex-col gap-2.5">
              <span className="text-brand-fg/40 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                COMPANY
              </span>
              <Link to="/research" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Research
              </Link>
              <Link to="/about" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                About
              </Link>
              <Link to="/contact" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Contact
              </Link>
            </div>
            <div className="flex flex-col gap-2.5">
              <span className="text-brand-fg/40 font-mono text-[11.5px] font-semibold tracking-[0.14em]">
                FOR RESIDENTS
              </span>
              <Link to="/stay-safe" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Stay Safe
              </Link>
              <Link to="/dashboard" className="text-brand-fg/70 font-sans text-[13.5px] font-medium transition-colors hover:text-brand-fg hover:underline hover:underline-offset-4 hover:decoration-brand-gold/60">
                Dashboard
              </Link>
            </div>
          </nav>
        </div>
        <div className="border-brand-fg/5 text-brand-fg/35 border-t px-4 py-4.5 text-center font-mono text-xs sm:px-6 lg:px-8">
          © 2026 EleTect · Kerala, India · IEEE IAS CMD & Amarnath Raja Humanitarian Awards 2025
        </div>
      </footer>
    </div>
  )
}
