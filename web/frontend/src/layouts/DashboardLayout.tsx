import { Outlet } from 'react-router-dom'

export function DashboardLayout() {
  return (
    <div className="min-h-screen">
      <Outlet />
    </div>
  )
}
