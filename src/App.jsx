import { useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'

import ProtectedRoute from '@/components/ProtectedRoute'
import { AuthProvider } from '@/context/AuthContext'
import { AppStateProvider } from '@/context/AppStateContext'
import AppLayout from '@/layouts/AppLayout'

import Learn from '@/pages/Learn'
import Login from '@/pages/Login'
import Onboarding from '@/pages/Onboarding'
import Report from '@/pages/Report'
import Credits from '@/pages/Credits'
import Stage from '@/pages/Stage'
import Profile from '@/pages/Profile'

/** Scrolls to the top whenever the route changes. */
function ScrollToTop() {
  const { pathname } = useLocation()

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' })
  }, [pathname])

  return null
}

/**
 * Provider order matters:
 *   AuthProvider      who is signed in (tokens live in apiClient)
 *   AppStateProvider  server data for the signed-in user (needs AuthProvider)
 *
 * Routes:
 *   /login                     public
 *   /onboarding                signed in, no header or bottom navigation
 *   / /report /credits /stage /profile   signed in, inside the shared layout
 *
 * The guard only decides what the screen shows. The backend checks the token
 * on every request, so it is never the real security.
 */
export default function App() {
  return (
    <AuthProvider>
      <AppStateProvider>
        <ScrollToTop />

        <Routes>
          <Route path="login" element={<Login />} />

          <Route element={<ProtectedRoute />}>
            <Route path="onboarding" element={<Onboarding />} />

            <Route element={<AppLayout />}>
              <Route index element={<Learn />} />
              <Route path="report" element={<Report />} />
              <Route path="credits" element={<Credits />} />
              <Route path="stage" element={<Stage />} />
              <Route path="profile" element={<Profile />} />
            </Route>
          </Route>

          {/* Unknown URLs go back to Learn (which redirects to /login when signed out) */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AppStateProvider>
    </AuthProvider>
  )
}
