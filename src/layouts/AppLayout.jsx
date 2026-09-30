import { Outlet } from 'react-router-dom'

import Header from '@/components/Header'
import BottomNavigation, { DesktopNavigation } from '@/components/BottomNavigation'

/**
 * The shell shared by every page (see the nested route in App.jsx):
 *
 *   Header (logo, wordmark, profile, hero scene)
 *   <Outlet />            the current page
 *   BottomNavigation      fixed bar on phones and tablets
 *
 * From `lg` up, the bottom bar is hidden and the same links appear
 * inside the Header through its `nav` slot.
 *
 * Pages render only their own content. They never draw a header or a nav.
 */

export default function AppLayout() {
  return (
    <div className="relative min-h-dvh">
      <Header nav={<DesktopNavigation />} />

      {/* pb-nav keeps content clear of the fixed bottom bar (removed at lg, where the bar is hidden) */}
      <main className="mx-auto w-full max-w-app px-4 pb-nav md:max-w-tablet md:px-8 lg:max-w-desktop lg:pb-16">
        <Outlet />
      </main>

      <BottomNavigation />
    </div>
  )
}
