import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useVoiceDock, routeChanged } from "./useVoiceDock";
import { isBackIntent, isHomeIntent, isBookingsIntent, isLoginIntent } from "./voicecmd";

// Paths found in App.js when this was installed.
const PATHS = {"home": "/", "bookings": null, "login": "/login"};

function AppDock() {
  const navigate = useNavigate();
  const go = (path, msg) => {
    if (!path) return { say: "That page is not available here.", listen: true };
    navigate(path);
    return { say: msg, listen: false };
  };
  useVoiceDock({
    maxTurns: 4,
    onStart: () => ({ say: "Say home, my bookings, login or back. You can also just use the screen.", listen: true }),
    onText: (said) => {
      if (isBackIntent(said)) { navigate(-1); return { listen: false }; }
      if (isHomeIntent(said)) return go(PATHS.home, "Taking you home.");
      if (isBookingsIntent(said)) return go(PATHS.bookings, "Opening your bookings.");
      if (isLoginIntent(said)) return go(PATHS.login, "Opening login.");
      return { say: "Sorry. Say home, my bookings, login or back.", listen: true };
    },
  }, 0);
  return null;
}

// Every page gets the mic. The chat page has its own mic, so it is skipped there.
export default function GlobalVoice() {
  const { pathname } = useLocation();
  useEffect(() => { routeChanged(); }, [pathname]);
  if (pathname === PATHS.home) return null;
  return <AppDock />;
}
