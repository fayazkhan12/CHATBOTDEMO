import { useEffect, useRef } from "react";
import { mountDock, createFormGuide } from "./voicedock";

export { CHECKOUT_VOICE_FIELDS, highlightPay, markVoiceFlow, takeReserveFlow, routeChanged } from "./voicedock";

// config: { onStart(), onText(text), maxTurns } - read fresh on every turn.
// priority: pages use the default (1); the app-wide dock uses 0.
export function useVoiceDock(config, priority = 1) {
  const ref = useRef(config);
  ref.current = config;
  useEffect(() => {
    const dock = mountDock(() => ref.current, priority);
    return () => dock.destroy();
  }, [priority]);
}

// options: { fields, onValue(key, value), onDone() }
export function useFormGuide(options) {
  const optsRef = useRef(options);
  optsRef.current = options;
  const guide = useRef(null);
  if (!guide.current) guide.current = createFormGuide(() => optsRef.current);
  return guide.current;
}
