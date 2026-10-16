import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'

import { session } from '@/services/apiClient'
import * as authApi from '@/services/api/auth'

/**
 * NAADAMAYA session state. The ONE place that knows who is signed in.
 *
 *   const { status, user, isNewUser, signIn, signOut, refreshUser } = useAuth()
 *
 * status:
 *   'loading'          restoring the session on app start
 *   'authenticated'    signed in (user is set)
 *   'unauthenticated'  show the sign-in screen
 *
 * On start: if a refresh token is stored, the user is loaded (apiClient
 * refreshes the access token on its own). A network failure keeps the user in
 * 'loading' -> 'unauthenticated' ONLY when the server rejected the session;
 * with no connection the stored session is kept and `offline` is true.
 *
 * apiClient tells this context when the session ends anywhere (refresh
 * rejected, account deleted), so the app returns to sign-in on its own.
 */

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [status, setStatus] = useState(() => (session.hasRefreshToken() ? 'loading' : 'unauthenticated'))
  const [user, setUser] = useState(null)
  const [isNewUser, setIsNewUser] = useState(false)
  const [offline, setOffline] = useState(false)
  const mounted = useRef(true)

  const restore = useCallback(async () => {
    if (!session.hasRefreshToken()) {
      setStatus('unauthenticated')
      return
    }
    setStatus('loading')
    try {
      const me = await authApi.getMe()
      if (!mounted.current) return
      setUser(me)
      setOffline(false)
      setStatus('authenticated')
    } catch (err) {
      if (!mounted.current) return
      if (err?.isNetwork) {
        setOffline(true) // keep the stored session; let the user retry
        setStatus('unauthenticated')
      } else {
        session.clear('restore_failed')
      }
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    restore()
    const off = session.subscribe((event) => {
      if (event.type === 'cleared') {
        setUser(null)
        setIsNewUser(false)
        setStatus('unauthenticated')
      }
    })
    return () => {
      mounted.current = false
      off()
    }
  }, [restore])

  /** Call after a successful verifyOtp(). */
  const signIn = useCallback((result) => {
    setUser(result.user)
    setIsNewUser(Boolean(result.is_new_user))
    setOffline(false)
    setStatus('authenticated')
  }, [])

  const signOut = useCallback(async (options) => {
    await authApi.logout(options) // clears the session; the listener resets state
  }, [])

  const refreshUser = useCallback(async () => {
    const me = await authApi.getMe()
    setUser(me)
    return me
  }, [])

  const finishOnboarding = useCallback(() => {
    setIsNewUser(false)
    setUser((u) => (u ? { ...u, onboarding_completed: true } : u))
  }, [])

  const value = useMemo(
    () => ({ status, user, isNewUser, offline, signIn, signOut, refreshUser, finishOnboarding, retry: restore }),
    [status, user, isNewUser, offline, signIn, signOut, refreshUser, finishOnboarding, restore]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
