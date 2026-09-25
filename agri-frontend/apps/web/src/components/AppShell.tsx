import { useSession, useUnreadCount } from "@agri/core";
import { Bell } from "lucide-react";
import { useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { ErrorBoundary } from "./ErrorBoundary";
import { tabsFor } from "../lib/nav";
import { LanguageMenu, UserMenu } from "./menus";
import { NotificationDrawer } from "./NotificationDrawer";
import { SyncBadge } from "./SyncBadge";
import { ChatbotWidget } from "./ChatbotWidget";

/**
 * En-tête du template (marque, onglets, actions) :
 * - grand écran : onglets dans l'en-tête ;
 * - téléphone : barre d'onglets en bas d'écran (les onglets du template disparaissaient).
 */
export function AppShell() {
  const { user } = useSession();
  const tabs = tabsFor(user?.role);
  const { data: unread = 0 } = useUnreadCount();
  const [notifOpen, setNotifOpen] = useState(false);
  const mobileTabs = tabs.slice(0, 5);
  const location = useLocation();

  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-40 bg-white border-b border-neutral-200 pt-[env(safe-area-inset-top)]">
        <div className="max-w-7xl mx-auto px-3 sm:px-6 lg:px-8 h-14 flex items-center justify-between gap-3">
          <Link to="/" className="text-lg sm:text-xl font-bold tracking-tight text-neutral-900 hover:text-emerald-800 shrink-0">
            AgriSmart Bénin
          </Link>
          <nav className="hidden lg:flex items-center gap-5 text-sm font-medium" aria-label="Rubriques">
            {tabs.map((t) => (
              <NavLink
                key={t.label}
                to={t.to}
                end={t.to === "/"}
                className={({ isActive }) =>
                  `py-2 border-b-2 whitespace-nowrap ${isActive ? "border-emerald-800 text-emerald-950 font-bold" : "border-transparent text-neutral-600 hover:text-neutral-900 hover:border-neutral-300"}`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            <SyncBadge />
            <LanguageMenu />
            <button type="button"
              onClick={() => setNotifOpen(true)}
              aria-label={`Notifications (${unread} non lues)`}
              className="relative min-h-9 px-2 text-neutral-700 hover:bg-neutral-100 rounded border border-neutral-200 cursor-pointer"
            >
              <Bell className="w-4 h-4" aria-hidden />
              {unread > 0 && (
                <span className="absolute -top-1.5 -right-1.5 min-w-5 h-5 px-1 bg-red-600 text-white text-xs font-bold rounded-full flex items-center justify-center tabular-nums">
                  {unread > 9 ? "9+" : unread}
                </span>
              )}
            </button>
            <UserMenu />
          </div>
        </div>
      </header>

      <main className="flex-1 max-w-7xl w-full mx-auto px-3 sm:px-6 lg:px-8 py-5 sm:py-6 pb-28 lg:pb-8">
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
      </main>

      <nav
        aria-label="Rubriques"
        className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-white border-t border-neutral-200 pb-[env(safe-area-inset-bottom)]"
      >
        <div className="grid" style={{ gridTemplateColumns: `repeat(${mobileTabs.length + (tabs.length > 5 ? 1 : 0)}, minmax(0, 1fr))` }}>
          {mobileTabs.map((t) => (
            <NavLink
              key={t.label}
              to={t.to}
              end={t.to === "/"}
              className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-xs ${isActive ? "text-emerald-900 font-bold" : "text-neutral-600"}`}
            >
              {({ isActive }) => (
                <>
                  <t.icon className={`w-6 h-6 ${isActive ? "text-emerald-800" : ""}`} aria-hidden />
                  {t.short}
                </>
              )}
            </NavLink>
          ))}
          {tabs.length > 5 && (
            <NavLink to="/plus" className={({ isActive }) => `flex flex-col items-center gap-0.5 py-2 text-xs ${isActive ? "text-emerald-900 font-bold" : "text-neutral-600"}`}>
              <span className="w-6 h-6 grid place-items-center text-lg leading-none" aria-hidden>•••</span>
              Plus
            </NavLink>
          )}
        </div>
      </nav>

      <footer className="hidden lg:block bg-white border-t border-neutral-200 py-5">
        <div className="max-w-7xl mx-auto px-8 flex items-center justify-between text-xs text-neutral-500">
          <span>
            <span className="font-semibold text-neutral-800">AgriSmart Bénin</span> · République du Bénin
          </span>
          <span>Les propositions de l'IA sont indicatives et relues par des agents.</span>
        </div>
      </footer>

      <NotificationDrawer open={notifOpen} onClose={() => setNotifOpen(false)} />
      <ChatbotWidget />
    </div>
  );
}
