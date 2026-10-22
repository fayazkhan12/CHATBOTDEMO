import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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

const QUICK_STARTERS = [
  { label: "Jaipur hotel chahiye", icon: Hotel },
  { label: "Delhi to Goa flight", icon: Plane },
  { label: "Mumbai to Pune bus", icon: BusFront },
  { label: "Airport cab Bangalore", icon: Car },
];

const MessageBubble = ({ msg, onOpenCard }) => (
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
          {msg.cards.map(card => (
            <article key={card.id} className="inline-card" onClick={() => onOpenCard(card)} data-testid={`inline-card-${card.id}`}>
              <img src={card.image} alt={card.title}/>
              <div className="inline-body">
                <span className="inline-type">{card.type}</span>
                <h4>{card.title}</h4>
                <small>{card.brand}</small>
                <div className="inline-footer">
                  <strong>₹{Number(card.price).toLocaleString("en-IN")}</strong>
                  <button className="inline-cta" data-testid={`inline-book-${card.id}`}>View <ArrowRight size={12}/></button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </div>
  </div>
);

export default function Home() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [messages, setMessages] = useState([
    { id: "greet", role: "assistant", text: "Namaste! Main DestinoWay — aapka travel agent. Flight, hotel, bus ya cab — kya chahiye bataiye? Aap koi bhi language me baat kar sakte ho." },
  ]);
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speakingReply, setSpeakingReply] = useState(false);
  const [voiceOutput, setVoiceOutput] = useState(true);
  const [sending, setSending] = useState(false);
  const recognition = useRef(null);
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
      const { data } = await http.post("/travel/search", {
        service: intent.service,
        origin: intent.origin || "Delhi",
        destination: intent.destination,
        ...(intent.destination_id ? { destination_id: intent.destination_id } : {}),
        start_date: intent.start_date,
        end_date: intent.end_date || intent.start_date,
        travellers: Number(intent.travellers || 2),
        ...(intent.budget_tier ? { budget_tier: intent.budget_tier } : {}),
        ...(intent.budget ? { budget: Number(intent.budget) } : {}),
      });
      await http.post("/travel/cache", data.results).catch(() => {});
      const top3 = data.results.slice(0, 3);
      setMessages((prev) => prev.map((m) => m.id === replyId ? { ...m, cards: top3 } : m));
    } catch (e) {
      setMessages((prev) => [...prev, { id: `err-${Date.now()}`, role: "assistant", text: "Search abhi fail ho gaya. Thodi der me try karein." }]);
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
              const { clean } = extractSearchIntent(answer);
              setMessages((old) => old.map((m) => m.id === replyId ? { ...m, text: clean } : m));
            }
          } catch { /* ignore */ }
        }
      }
    } catch {
      answer = "Concierge se connect nahi ho pa raha. Thodi der me try karein.";
      setMessages((old) => old.map((m) => m.id === replyId ? { ...m, text: answer } : m));
    } finally {
      setSending(false);
    }

    const { clean, intent } = extractSearchIntent(answer);
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

  const toggleVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("Voice input not supported in this browser."); return; }
    if (listening) { recognition.current?.stop(); setListening(false); return; }
    const r = new SR();
    r.lang = "en-IN"; // auto-detect at system; backend will handle actual language
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      const said = e.results[0][0].transcript;
      setText(said);
      send(said, { fromVoice: true });
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recognition.current = r;
    r.start();
    setListening(true);
  };

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
          <MessageBubble key={m.id} msg={m} onOpenCard={openCard}/>
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
          title={listening ? "Stop listening" : "Talk — Hindi, English, Bengali and more"}
        >
          <Mic size={18}/>
        </button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={listening ? "Listening…" : sending ? "AI typing… ya nayi baat type karein" : "Message DestinoWay — koi bhi language me…"}
          autoFocus
          data-testid="agent-input"
        />
        <button type="submit" className="icon-btn primary" aria-label="Send" disabled={sending || !text.trim()} data-testid="agent-send">
          <Send size={18}/>
        </button>
      </form>

      <div className="agent-hint">
        <button className="link-btn" onClick={() => navigate("/search")}>RAVI AI</button>
      </div>
    </div>
  );
}
