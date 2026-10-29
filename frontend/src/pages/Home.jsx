import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createVoiceEngine, VOICE_LANGS, shouldSendUtterance, describeStop, pickDefaultLang, saveLang } from "../lib/voice";
import { resolvePick, hasPickIntent, isStrongReserve } from "../lib/voicecmd";
import { guardReply } from "../lib/guard";
import { markVoiceFlow } from "../lib/voicedock";
import { useNavigate } from "react-router-dom";
import { Mic, Send, Sparkles, Plane, Hotel, BusFront, Car, Volume2, VolumeX, ArrowRight } from "lucide-react";
import { API, http } from "../lib/api";
import { useAuth } from "../lib/auth";

// --- voice helpers ---
function pickBestVoice(script) {
  const voices = window.speechSynthesis?.getVoices() || [];
  if (!voices.length) return null;
  const want = script === "hi" ? ["hi-IN"] : ["en-IN", "en-GB", "en-US"];
  // prefer Google / Microsoft Neural voices
  for (const lang of want) {
    const neural = voices.find(v => v.lang === lang && /google|neural|natural|online/i.test(v.name));
    if (neural) return neural;
    const any = voices.find(v => v.lang === lang);
    if (any) return any;
  }
  return voices[0];
}

function speak(text, { onEnd } = {}) {
  if (!("speechSynthesis" in window) || !text) { onEnd?.(); return; }
  window.speechSynthesis.cancel();
  const hasDev = /[\u0900-\u097F]/.test(text);
  const script = hasDev ? "hi" : "en";
  const u = new SpeechSynthesisUtterance(text);
  const v = pickBestVoice(script);
  if (v) u.voice = v;
  u.lang = v?.lang || (hasDev ? "hi-IN" : "en-IN");
  u.rate = 0.98;
  u.pitch = 1.02;
  u.volume = 1;
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  window.speechSynthesis.speak(u);
}

// Parse <search>{...}</search> block out of the streamed reply
function extractSearchIntent(text) {
  const match = text.match(/<search>\s*([\s\S]*?)\s*<\/search>/i);
  if (!match) return { clean: text, intent: null };
  try {
    const intent = JSON.parse(match[1]);
    const clean = text.replace(match[0], "").trim();
    return { clean, intent };
  } catch {
    return { clean: text.replace(match[0], "").trim(), intent: null };
  }
}

// Labels under the result cards, in the language the user wrote in
const LABELS = {
  en: {
    more: (n) => `Show more (${n} more)`,
    next: "Show next options",
    found: (a, b) => `${a} options found, showing ${b}`,
    loading: "Loading...",
  },
  hinglish: {
    more: (n) => `Aur dikhao (${n} aur)`,
    next: "Agle options dikhao",
    found: (a, b) => `${a} options mile, ${b} dikha rahe hain`,
    loading: "Loading...",
  },
  hi: {
    more: (n) => `\u0914\u0930 \u0926\u093f\u0916\u093e\u0913 (${n} \u0914\u0930)`,
    next: "\u0905\u0917\u0932\u0947 \u0935\u093f\u0915\u0932\u094d\u092a \u0926\u093f\u0916\u093e\u0913",
    found: (a, b) => `${a} \u0935\u093f\u0915\u0932\u094d\u092a \u092e\u093f\u0932\u0947, ${b} \u0926\u093f\u0916\u093e \u0930\u0939\u0947 \u0939\u0948\u0902`,
    loading: "\u0932\u094b\u0921 \u0939\u094b \u0930\u0939\u093e \u0939\u0948...",
  },
};

function detectUiLang(text) {
  const t = text || "";
  if (/[\u0900-\u097F]/.test(t)) return "hi";
  if (/\b(hai|hain|chahiye|chahie|dikhao|dikha|mujhe|kya|nahi|karo|batao|mein|wala|wale|liye|kaise|kitna|aur|bhi)\b/i.test(t)) return "hinglish";
  return "en";
}

const QUICK_STARTERS = [
  { label: "Hotels in Jaipur", icon: Hotel },
  { label: "Delhi to Goa flight", icon: Plane },
  { label: "Mumbai to Pune bus", icon: BusFront },
  { label: "Airport cab Bangalore", icon: Car },
];

const MessageBubble = ({ msg, onOpenCard, onMore }) => (
  <div className={`chat-row ${msg.role}`} data-testid={`chat-row-${msg.role}`}>
    <div className="chat-avatar-lg">
      {msg.role === "assistant" ? <Sparkles size={16} /> : <span>You</span>}
    </div>
    <div className="chat-bubble-wrap">
      <div className="chat-bubble-lg">
        {msg.text || <span className="typing-dots"><i/><i/><i/></span>}
      </div>
      {msg.cards?.length > 0 && (
        <div className="inline-cards">
          {msg.cards.slice(0, msg.visible || 3).map(card => (
            <article key={card.id} className="inline-card" onClick={() => onOpenCard(card)} data-testid={`inline-card-${card.id}`}>
              <img src={card.image} alt={card.title}/>
              <div className="inline-body">
                <span className="inline-type">{card.type}{card.mode !== "LIVE" && <em className="demo-chip">Demo</em>}</span>
                <h4>{card.title}</h4>
                <small>{card.brand}</small>
                <div className="inline-footer">
                  <strong>₹{Math.round(Number(card.price) || 0).toLocaleString("en-IN")}</strong>
                  <button className="inline-cta" data-testid={`inline-book-${card.id}`}>View <ArrowRight size={12}/></button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
      {msg.cards?.length > 0 && (
        <div className="cards-more" style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap", marginTop: 10 }}>
          {msg.total > 0 && (
            <small style={{ color: "var(--muted)" }}>
              {(LABELS[msg.lang] || LABELS.en).found(msg.total, Math.min(msg.visible || 3, msg.cards.length))}
            </small>
          )}
          {(msg.cards.length > (msg.visible || 3) || msg.hasMore) && (
            <button className="inline-cta" disabled={!!msg.loadingMore} onClick={() => onMore(msg)} data-testid="show-more">
              {msg.loadingMore
                ? (LABELS[msg.lang] || LABELS.en).loading
                : msg.cards.length > (msg.visible || 3)
                  ? (LABELS[msg.lang] || LABELS.en).more(msg.cards.length - (msg.visible || 3))
                  : (LABELS[msg.lang] || LABELS.en).next}
            </button>
          )}
        </div>
      )}
    </div>
  </div>
);

export default function Home() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [messages, setMessages] = useState([
    { id: "greet", role: "assistant", text: "Hi! I am DestinoWay, your travel concierge. Hotels, flights, buses or cabs: what do you need? You can talk to me in any language." },
  ]);
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speakingReply, setSpeakingReply] = useState(false);
  const [voiceOutput, setVoiceOutput] = useState(true);
  const [sending, setSending] = useState(false);
  const endRef = useRef(null);
  const voiceModeRef = useRef(false); // true for current send if invoked via mic
  const historyRef = useRef([]); // mirrors conversation for backend

  // keep history in sync with messages
  useEffect(() => {
    historyRef.current = messages
      .filter((m) => m.text && m.id !== "greet")
      .map((m) => ({ role: m.role, text: m.text }));
  }, [messages]);

  // warm up voices list on mount
  useEffect(() => { window.speechSynthesis?.getVoices(); }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  const openCard = (card) => {
    http.post("/travel/cache", [card]).catch(() => {});
    const service = card.type === "flight" ? "flights" : card.type === "hotel" ? "hotels" : card.type === "bus" ? "buses" : "cabs";
    navigate(`/detail/${service}/${encodeURIComponent(card.id)}`);
  };

  const runSearch = async (intent, replyId) => {
    try {
      const body = {
        service: intent.service,
        origin: intent.origin || "Delhi",
        destination: intent.destination,
        ...(intent.destination_id ? { destination_id: intent.destination_id } : {}),
        start_date: intent.start_date,
        end_date: intent.end_date || intent.start_date,
        travellers: Number(intent.travellers || 2),
        ...(intent.budget_tier ? { budget_tier: intent.budget_tier } : {}),
        ...(intent.budget ? { budget: Number(intent.budget) } : {}),
      };
      const { data } = await http.post("/travel/search", body);
      await http.post("/travel/cache", data.results).catch(() => {});
      setMessages((prev) => prev.map((m) => m.id === replyId ? {
        ...m, cards: data.results, visible: 3, total: data.total || 0,
        page: data.page || 1, hasMore: !!data.has_more, searchBody: body,
        lang: detectUiLang([...historyRef.current].reverse().find((h) => h.role === "user")?.text),
      } : m));
    } catch (e) {
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: "assistant", text: "Search failed. Please try again in a moment." }]);
    }
  };

  const loadMore = async (msg) => {
    if (msg.loadingMore) return;
    const hidden = (msg.cards?.length || 0) - (msg.visible || 3);
    if (hidden > 0) {
      setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, visible: (m.visible || 3) + 6 } : m));
      return;
    }
    if (!msg.hasMore || !msg.searchBody) return;
    setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, loadingMore: true } : m));
    try {
      const { data } = await http.post("/travel/search", { ...msg.searchBody, page: (msg.page || 1) + 1 });
      await http.post("/travel/cache", data.results).catch(() => {});
      setMessages((prev) => prev.map((m) => {
        if (m.id !== msg.id) return m;
        const seen = new Set(m.cards.map((c) => c.id));
        const fresh = data.results.filter((c) => !seen.has(c.id));
        const all = [...m.cards, ...fresh];
        return { ...m, cards: all, visible: all.length, page: data.page || (m.page || 1) + 1, hasMore: !!data.has_more && fresh.length > 0, loadingMore: false };
      }));
    } catch (e) {
      setMessages((prev) => prev.map((m) => m.id === msg.id ? { ...m, loadingMore: false } : m));
    }
  };

  const send = useCallback(async (preset, { fromVoice = false } = {}) => {
    const t = (preset ?? text).trim();
    if (!t || sending) return;
    voiceModeRef.current = fromVoice;
    setText("");
    setSending(true);

    const userId = `u-${Date.now()}`;
    const replyId = `a-${Date.now() + 1}`;
    const userMsg = { id: userId, role: "user", text: t };
    const placeholder = { id: replyId, role: "assistant", text: "", streaming: true };
    setMessages((old) => [...old, userMsg, placeholder]);

    let answer = "";
    try {
      const resp = await fetch(`${API}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: t,
          language: "auto",
          history: historyRef.current.slice(-10),
          context: { user: user?.name || null },
        }),
      });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop();
        for (const chunk of chunks) {
          const line = chunk.split("\n").find((x) => x.startsWith("data: "));
          if (!line) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.text) {
              answer += ev.text;
              const clean = guardReply(extractSearchIntent(answer).clean);
              setMessages((old) => old.map((m) => m.id === replyId ? { ...m, text: clean } : m));
            }
          } catch { /* ignore */ }
        }
      }
    } catch {
      answer = "Cannot reach the concierge right now. Please try again shortly.";
      setMessages((old) => old.map((m) => m.id === replyId ? { ...m, text: answer } : m));
    } finally {
      setSending(false);
    }

    const { clean: rawClean, intent } = extractSearchIntent(answer);
    const clean = guardReply(rawClean);
    setMessages((old) => old.map((m) => m.id === replyId ? { ...m, text: clean } : m));

    if (intent?.service && intent?.destination) {
      await runSearch(intent, replyId);
    }

    if (voiceModeRef.current && voiceOutput && clean) {
      setSpeakingReply(true);
      speak(clean, { onEnd: () => setSpeakingReply(false) });
    }
    voiceModeRef.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, sending, user, voiceOutput]);

  // ---- hands-free voice mode ----
  const [voiceLang, setVoiceLang] = useState(pickDefaultLang);
  const [interim, setInterim] = useState("");
  const [voiceNote, setVoiceNote] = useState("");
  const voiceRef = useRef(null);
  const sendRef = useRef(null);
  const sendingRef = useRef(false);
  const chatActiveRef = useRef(false);
  const pendingVoice = useRef("");
  sendRef.current = send;
  sendingRef.current = sending;
  chatActiveRef.current = messages.length > 1;
  const lastCardsRef = useRef([]);
  const openCardRef = useRef(null);
  openCardRef.current = openCard;
  const lastCardMsg = [...messages].reverse().find((m) => m.cards && m.cards.length);
  lastCardsRef.current = lastCardMsg ? lastCardMsg.cards.slice(0, lastCardMsg.visible || 3) : [];

  const onVoiceFinal = useCallback((said) => {
    if (!shouldSendUtterance(said, chatActiveRef.current)) {
      setVoiceNote("I did not catch that. Tap the mic and try again.");
      return;
    }
    const pick = resolvePick(said, lastCardsRef.current);
    if (pick) {
      markVoiceFlow(isStrongReserve(said) ? "reserve" : undefined);
      openCardRef.current(pick);
      return;
    }
    if (lastCardsRef.current.length && hasPickIntent(said)) {
      setVoiceNote("I could not tell which one. Say first, second, third, or the hotel name.");
      return;
    }
    if (sendingRef.current) {
      pendingVoice.current = `${pendingVoice.current} ${said}`.trim();
      return;
    }
    sendRef.current(said, { fromVoice: true });
  }, []);

  useEffect(() => {
    if (!sending && pendingVoice.current) {
      const queued = pendingVoice.current;
      pendingVoice.current = "";
      sendRef.current(queued, { fromVoice: true });
    }
  }, [sending]);

  const stopVoice = useCallback((reason) => {
    if (voiceRef.current) voiceRef.current.destroy();
    voiceRef.current = null;
    if (reason !== "done") pendingVoice.current = "";
    setListening(false);
    setInterim("");
    if (reason !== "done") setVoiceNote(reason ? describeStop(reason) : "");
  }, []);

  const toggleVoice = () => {
    if (listening) { stopVoice(); return; }
    setVoiceNote("");
    const eng = createVoiceEngine({
      lang: voiceLang,
      onInterim: setInterim,
      onFinal: onVoiceFinal,
      onStop: stopVoice,
      once: true,
      idleMs: 12000,
    });
    if (!eng) { setVoiceNote(describeStop("unsupported")); return; }
    voiceRef.current = eng;
    eng.start();
    setListening(true);
  };

  const changeVoiceLang = (code) => {
    setVoiceLang(code);
    saveLang(code);
    if (voiceRef.current) voiceRef.current.setLang(code);
  };

  // do not listen while the bot is speaking (it would hear itself)
  useEffect(() => {
    if (voiceRef.current) voiceRef.current.setPaused(speakingReply);
  }, [speakingReply]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => { if (voiceRef.current) voiceRef.current.destroy(); }, []);

  const stopSpeaking = () => {
    window.speechSynthesis?.cancel();
    setSpeakingReply(false);
  };

  const showStarters = messages.length <= 1;

  return (
    <div className="agent-page" data-testid="agent-page">
      <div className="agent-header">
        <div className="agent-identity">
          <div className="agent-avatar"><Sparkles size={20}/></div>
          <div>
            <div className="agent-name">DestinoWay AI</div>
            <div className="agent-status">
           
            </div>
          </div>
        </div>
        <div className="agent-actions">
          <button
            className={voiceOutput ? "icon-btn primary" : "icon-btn"}
            title={voiceOutput ? "Voice reply on" : "Voice reply off"}
            onClick={() => { setVoiceOutput(v => !v); if (voiceOutput) stopSpeaking(); }}
            data-testid="toggle-voice-output"
          >
            {voiceOutput ? <Volume2 size={16}/> : <VolumeX size={16}/>}
          </button>
          {speakingReply && (
            <button className="icon-btn" onClick={stopSpeaking} data-testid="stop-speaking">Stop</button>
          )}
        </div>
      </div>

      <div className="agent-messages" data-testid="agent-messages">
        {messages.map((m) => (
          <MessageBubble key={m.id} msg={m} onOpenCard={openCard} onMore={loadMore}/>
        ))}
        <div ref={endRef}/>
      </div>

      {showStarters && (
        <div className="agent-starters">
          <div className="starter-label">Try saying</div>
          <div className="starter-chips">
            {QUICK_STARTERS.map((s, i) => {
              const Icon = s.icon;
              return (
                <button key={i} onClick={() => send(s.label)} data-testid={`starter-${i}`}>
                  <Icon size={13}/> {s.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <form
        className="agent-compose"
        onSubmit={(e) => { e.preventDefault(); send(undefined, { fromVoice: false }); }}
      >
        <button
          type="button"
          className={listening ? "icon-btn listening" : "icon-btn"}
          onClick={toggleVoice}
          aria-label="Voice input"
          data-testid="voice-mic-btn"
          title={listening ? "Stop listening" : "Tap and speak"}
        >
          <Mic size={18}/>
        </button>
        <select
          className="voice-lang"
          value={voiceLang}
          onChange={(e) => changeVoiceLang(e.target.value)}
          aria-label="Voice language"
          data-testid="voice-lang"
        >
          {VOICE_LANGS.map((l) => (
            <option key={l.code} value={l.code}>{l.label}</option>
          ))}
        </select>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={listening ? (interim || "Listening...") : sending ? "Thinking... you can type your next message" : "Message DestinoWay in any language..."}
          autoFocus
          data-testid="agent-input"
        />
        <button type="submit" className="icon-btn primary" aria-label="Send" disabled={sending || !text.trim()} data-testid="agent-send">
          <Send size={18}/>
        </button>
      </form>

      {listening && (
        <div className="voice-live" role="status">
          <span className="voice-dot" /> Listening... speak now. The mic turns off by itself.
        </div>
      )}
      {voiceNote && <div className="voice-note" role="status">{voiceNote}</div>}

    </div>
  );
}
