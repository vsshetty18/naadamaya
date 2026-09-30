import { useEffect } from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'

import { AppStateProvider } from '@/context/AppStateContext'
import AppLayout from '@/layouts/AppLayout'

import Learn from '@/pages/Learn'
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

export default function App() {
  return (
    <AppStateProvider>
      <ScrollToTop />

      <Routes>
        {/* Every page shares the same layout: Header + content + BottomNavigation */}
        <Route element={<AppLayout />}>
          <Route index element={<Learn />} />
          <Route path="report" element={<Report />} />
          <Route path="credits" element={<Credits />} />
          <Route path="stage" element={<Stage />} />
          <Route path="profile" element={<Profile />} />
        </Route>

        {/* Unknown URLs go back to Learn */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </AppStateProvider>
  )
}
