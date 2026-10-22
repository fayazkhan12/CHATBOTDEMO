import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function AuthCallback() {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const processed = useRef(false);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) { navigate("/login"); return; }
    const sessionId = match[1];
    http.post("/auth/session", null, { headers: { "X-Session-ID": sessionId } })
      .then(async () => {
        await refresh();
        window.history.replaceState(null, "", "/dashboard");
        navigate("/dashboard", { replace: true });
      })
      .catch(() => navigate("/login", { replace: true }));
  }, [navigate, refresh]);

  return (
    <div style={{display:'grid',placeItems:'center',minHeight:'100vh',color:'var(--muted)',fontFamily:'Manrope'}}>
      <div><span className="spinner"/> Finalising sign-in…</div>
    </div>
  );
}
