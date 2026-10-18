import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { Loader2, WifiOff } from 'lucide-react'

import Button from '@/components/Button'
import logoMark from '@/assets/logo-mark.png'
import { useAuth } from '@/context/AuthContext'

/**
 * Route guard. Wraps every page that needs a signed-in user.
 *
 *   <Route element={<ProtectedRoute />}> ...pages... </Route>
 *
 *   loading          a calm full-screen splash while the session is restored
 *   offline          a retry screen (the stored session is kept, not discarded)
 *   unauthenticated  redirect to /login, remembering where the user was going
 *   new user         redirect to /onboarding once, until it is finished or skipped
 *
 * This is only a convenience for the screen. The backend independently checks
 * the token on every request, so hiding a page here is never the security.
 */

function Splash({ children }) {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 px-6 text-center">
      <img src={logoMark} alt="" className="h-20 w-20 object-contain" draggable="false" />
      {children}
    </div>
  )
}

export default function ProtectedRoute() {
  const { status, user, isNewUser, offline, retry } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return (
      <Splash>
        <Loader2 className="h-6 w-6 animate-spin text-brown-400" aria-hidden="true" />
        <p className="sr-only" role="status">Loading NAADAMAYA</p>
      </Splash>
    )
  }

  if (status === 'unauthenticated') {
    if (offline) {
      return (
        <Splash>
          <WifiOff className="h-7 w-7 text-brown-400" strokeWidth={1.6} aria-hidden="true" />
          <h1 className="font-serif text-[1.6rem] font-semibold text-brown-900">No connection</h1>
          <p className="max-w-xs text-[0.9rem] text-brown-500">
            We could not reach NAADAMAYA. You are still signed in. Check your connection and try again.
          </p>
          <Button variant="primary" onClick={retry}>Try again</Button>
        </Splash>
      )
    }
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  const needsOnboarding = isNewUser && user && !user.onboarding_completed
  if (needsOnboarding && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />
  }

  return <Outlet />
}
