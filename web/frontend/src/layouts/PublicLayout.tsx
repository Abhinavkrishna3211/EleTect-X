import { Link, NavLink, Outlet } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/technology', label: 'Technology' },
  { to: '/solutions', label: 'Solutions' },
  { to: '/deployments', label: 'Deployments' },
  { to: '/research', label: 'Research' },
  { to: '/about', label: 'About' },
  { to: '/contact', label: 'Contact' },
  { to: '/stay-safe', label: 'Stay Safe' },
]

export function PublicLayout() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-border border-b">
        <nav className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <Link to="/" className="font-semibold tracking-tight">
            EleTect
          </Link>
          <ul className="hidden flex-wrap items-center gap-6 text-sm md:flex">
            {NAV_LINKS.map((link) => (
              <li key={link.to}>
                <NavLink
                  to={link.to}
                  end={link.end}
                  className={({ isActive }) => (isActive ? 'font-medium' : 'text-muted-foreground')}
                >
                  {link.label}
                </NavLink>
              </li>
            ))}
          </ul>
          <Link
            to="/dashboard"
            className="bg-primary text-primary-foreground rounded-md px-4 py-2 text-sm font-medium"
          >
            Dashboard login
          </Link>
        </nav>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-border text-muted-foreground border-t px-6 py-8 text-sm">
        <div className="mx-auto max-w-6xl">EleTect. Protecting farms, forests, and the future.</div>
      </footer>
    </div>
  )
}
