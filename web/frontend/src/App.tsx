import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { PublicLayout } from '@/layouts/PublicLayout'
import { Home } from '@/pages/public/Home'
import { Login } from '@/pages/auth/Login'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { RoleGate } from '@/components/RoleGate'

// Home and Login are the two entry points a cold visitor actually lands on, so
// they stay in the main bundle. Everything else is split.
//
// The dashboard is the reason this matters: it pulls in Leaflet and the whole
// charting surface, and before this split every anonymous visitor to the
// marketing site downloaded all of it (a single 740 kB chunk) to read a page
// that renders none of it. A forest officer on a phone at the edge of a
// reserve is the person who pays for that, so the dashboard now loads only
// when someone actually signs in.
const Technology = lazy(() => import('@/pages/public/Technology').then((m) => ({ default: m.Technology })))
const Solutions = lazy(() => import('@/pages/public/Solutions').then((m) => ({ default: m.Solutions })))
const Deployments = lazy(() => import('@/pages/public/Deployments').then((m) => ({ default: m.Deployments })))
const Research = lazy(() => import('@/pages/public/Research').then((m) => ({ default: m.Research })))
const About = lazy(() => import('@/pages/public/About').then((m) => ({ default: m.About })))
const Contact = lazy(() => import('@/pages/public/Contact').then((m) => ({ default: m.Contact })))
const StaySafe = lazy(() => import('@/pages/public/StaySafe').then((m) => ({ default: m.StaySafe })))

const Signup = lazy(() => import('@/pages/auth/Signup').then((m) => ({ default: m.Signup })))
const ForgotPassword = lazy(() =>
  import('@/pages/auth/ForgotPassword').then((m) => ({ default: m.ForgotPassword })),
)
const ResetPassword = lazy(() =>
  import('@/pages/auth/ResetPassword').then((m) => ({ default: m.ResetPassword })),
)

const DashboardLayout = lazy(() =>
  import('@/layouts/DashboardLayout').then((m) => ({ default: m.DashboardLayout })),
)
const DashboardIndex = lazy(() =>
  import('@/pages/dashboard/DashboardIndex').then((m) => ({ default: m.DashboardIndex })),
)
const Overview = lazy(() => import('@/pages/dashboard/Overview').then((m) => ({ default: m.Overview })))
const Replay = lazy(() => import('@/pages/dashboard/Replay').then((m) => ({ default: m.Replay })))
const Corridor = lazy(() => import('@/pages/dashboard/Corridor').then((m) => ({ default: m.Corridor })))
const Learning = lazy(() => import('@/pages/dashboard/Learning').then((m) => ({ default: m.Learning })))
const Fleet = lazy(() => import('@/pages/dashboard/Fleet').then((m) => ({ default: m.Fleet })))
const Planner = lazy(() => import('@/pages/dashboard/Planner').then((m) => ({ default: m.Planner })))
const Demo = lazy(() => import('@/pages/dashboard/Demo').then((m) => ({ default: m.Demo })))
const OfficerApprovals = lazy(() =>
  import('@/pages/dashboard/OfficerApprovals').then((m) => ({ default: m.OfficerApprovals })),
)
const Admin = lazy(() => import('@/pages/dashboard/Admin').then((m) => ({ default: m.Admin })))

// Matches ProtectedRoute's own loading state, so a chunk fetch and a session
// check look like one continuous load rather than two different spinners.
function RouteFallback() {
  return (
    <div className="bg-brand-bg grid min-h-screen place-items-center">
      <span className="text-brand-fg/50 font-mono text-xs">Loading…</span>
    </div>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route element={<PublicLayout />}>
            <Route index element={<Home />} />
            <Route path="technology" element={<Technology />} />
            <Route path="solutions" element={<Solutions />} />
            <Route path="deployments" element={<Deployments />} />
            <Route path="research" element={<Research />} />
            <Route path="about" element={<About />} />
            <Route path="contact" element={<Contact />} />
            <Route path="stay-safe" element={<StaySafe />} />
          </Route>

          <Route path="login" element={<Login />} />
          <Route path="signup" element={<Signup />} />
          <Route path="forgot-password" element={<ForgotPassword />} />
          <Route path="reset-password" element={<ResetPassword />} />

          <Route
            path="dashboard"
            element={
              <ProtectedRoute>
                <DashboardLayout />
              </ProtectedRoute>
            }
          >
            <Route index element={<DashboardIndex />} />
            <Route
              path="overview"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Overview />
                </RoleGate>
              }
            />
            <Route
              path="replay"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Replay />
                </RoleGate>
              }
            />
            <Route
              path="network"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Corridor />
                </RoleGate>
              }
            />
            <Route
              path="learning"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Learning />
                </RoleGate>
              }
            />
            <Route
              path="fleet"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Fleet />
                </RoleGate>
              }
            />
            <Route
              path="planner"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Planner />
                </RoleGate>
              }
            />
            <Route
              path="demo"
              element={
                <RoleGate roles={['officer', 'admin']}>
                  <Demo />
                </RoleGate>
              }
            />
            <Route
              path="officers"
              element={
                <RoleGate roles={['admin']}>
                  <OfficerApprovals />
                </RoleGate>
              }
            />
            <Route
              path="admin"
              element={
                <RoleGate roles={['admin']}>
                  <Admin />
                </RoleGate>
              }
            />
          </Route>
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}

export default App
