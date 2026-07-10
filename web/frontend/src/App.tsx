import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { PublicLayout } from '@/layouts/PublicLayout'
import { DashboardLayout } from '@/layouts/DashboardLayout'
import { Home } from '@/pages/public/Home'
import { Technology } from '@/pages/public/Technology'
import { Solutions } from '@/pages/public/Solutions'
import { Deployments } from '@/pages/public/Deployments'
import { Research } from '@/pages/public/Research'
import { About } from '@/pages/public/About'
import { Contact } from '@/pages/public/Contact'
import { StaySafe } from '@/pages/public/StaySafe'
import { Login } from '@/pages/auth/Login'
import { Signup } from '@/pages/auth/Signup'
import { ForgotPassword } from '@/pages/auth/ForgotPassword'
import { ResetPassword } from '@/pages/auth/ResetPassword'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { RoleGate } from '@/components/RoleGate'
import { DashboardIndex } from '@/pages/dashboard/DashboardIndex'
import { OfficerApprovals } from '@/pages/dashboard/OfficerApprovals'
import { Overview } from '@/pages/dashboard/Overview'
import { Replay } from '@/pages/dashboard/Replay'
import { Corridor } from '@/pages/dashboard/Corridor'
import { Learning } from '@/pages/dashboard/Learning'
import { Fleet } from '@/pages/dashboard/Fleet'
import { PlaceholderPanel } from '@/pages/dashboard/PlaceholderPanel'

function App() {
  return (
    <BrowserRouter>
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
                <PlaceholderPanel title="Deployment planner" />
              </RoleGate>
            }
          />
          <Route
            path="demo"
            element={
              <RoleGate roles={['officer', 'admin']}>
                <PlaceholderPanel title="Demo mode" />
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
                <PlaceholderPanel title="Administration" />
              </RoleGate>
            }
          />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
