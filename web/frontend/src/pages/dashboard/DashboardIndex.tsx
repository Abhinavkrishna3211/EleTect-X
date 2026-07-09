import { Navigate } from 'react-router-dom'
import { useAuth } from '@/lib/auth'
import { ResidentView } from '@/pages/dashboard/ResidentView'

export function DashboardIndex() {
  const { profile } = useAuth()

  if (!profile) return null
  if (profile.role === 'public') return <ResidentView />
  return <Navigate to="/dashboard/overview" replace />
}
