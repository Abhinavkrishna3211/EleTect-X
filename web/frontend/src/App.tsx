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
import { Dashboard } from '@/pages/dashboard/Dashboard'

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
        <Route path="dashboard" element={<DashboardLayout />}>
          <Route index element={<Dashboard />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
