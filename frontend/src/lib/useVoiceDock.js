import { useEffect, useRef } from "react";
import { mountDock, createFormGuide } from "./voicedock";

export { CHECKOUT_VOICE_FIELDS, highlightPay, markVoiceFlow } from "./voicedock";

// config: { onStart(), onText(text), maxTurns } - read fresh on every turn.
export function useVoiceDock(config) {
  const ref = useRef(config);
  ref.current = config;
  useEffect(() => {
    const dock = mountDock(() => ref.current);
    return () => dock.destroy();
  }, []);
}

// options: { fields, onValue(key, value), onDone() }
export function useFormGuide(options) {
  const optsRef = useRef(options);
  optsRef.current = options;
  const guide = useRef(null);
  if (!guide.current) guide.current = createFormGuide(() => optsRef.current);
  return guide.current;
}
