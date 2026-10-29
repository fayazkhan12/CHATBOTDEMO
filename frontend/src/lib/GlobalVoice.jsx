import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useVoiceDock, routeChanged } from "./useVoiceDock";
import { isHomeIntent, isBookingsIntent, isLoginIntent } from "./voicecmd";
import { createPageGuide } from "./pageform";

// Paths found in App.js when this was installed.
const PATHS = {"home": "/", "bookings": "/dashboard", "login": "/login"};

const BACK_RE = /\b(go back|back|wapas|vapas|peeche)\b/;

function AppDock() {
  const navigate = useNavigate();
  const formRef = useRef(null);
  const go = (path, msg) => {
    if (!path) return { say: "That page is not available here.", listen: true };
    navigate(path);
    return { say: msg, listen: false };
  };
  useVoiceDock({
    maxTurns: 40,
    onStart: () => {
      formRef.current = createPageGuide();
      if (formRef.current) return formRef.current.start();
      return { say: "Say home, my bookings, login or back. You can also just use the screen.", listen: true };
    },
    onText: (said) => {
      if (BACK_RE.test(said.toLowerCase())) { navigate(-1); return { listen: false }; }
      if (formRef.current) return formRef.current.handle(said);
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
