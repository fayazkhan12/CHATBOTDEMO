import { useEffect, useRef, useState } from "react";
import { Mic, Send, Sparkles, X, Volume2, VolumeX } from "lucide-react";
import { API } from "../lib/api";

const SUGGESTIONS = [
  "Plan a 4-day Goa trip for 2 under ₹25,000",
  "Best honeymoon destinations in India for January",
  "Udaipur me kaunsa heritage hotel best hai?",
  "मुझे मालदीव के लिए 5 दिन का प्लान चाहिए",
];

// Pick the most natural-sounding voice available for a given language code.
function pickVoice(voices, langPref) {
  if (!voices || voices.length === 0) return null;
  const prefLang = langPref.toLowerCase();
  const scored = voices.map((v) => {
    const name = (v.name || "").toLowerCase();
    const lang = (v.lang || "").toLowerCase();
    let s = 0;
    if (lang.startsWith(prefLang.slice(0, 2))) s += 100;
    if (lang === prefLang) s += 50;
    // prefer neural / natural / online voices
    if (/neural|natural|wavenet|studio|online|premium|enhanced/.test(name)) s += 40;
    if (/google|microsoft/.test(name)) s += 20;
    // soft bonus for Indian locales
    if (lang.includes("in")) s += 10;
    // demote low-quality legacy voices
    if (/espeak|robot|classic/.test(name)) s -= 50;
    if (v.localService === false) s += 5; // cloud voices usually nicer
    return { v, s };
  });
  scored.sort((a, b) => b.s - a.s);
  return scored[0]?.v || null;
}

function detectLang(text) {
  if (/[\u0900-\u097F]/.test(text)) return "hi-IN"; // Devanagari (Hindi/Marathi)
  if (/[\u0980-\u09FF]/.test(text)) return "bn-IN"; // Bengali
  if (/[\u0B80-\u0BFF]/.test(text)) return "ta-IN"; // Tamil
  if (/[\u0C00-\u0C7F]/.test(text)) return "te-IN"; // Telugu
  if (/[\u0A80-\u0AFF]/.test(text)) return "gu-IN"; // Gujarati
  if (/[\u0C80-\u0CFF]/.test(text)) return "kn-IN"; // Kannada
  if (/[\u0D00-\u0D7F]/.test(text)) return "ml-IN"; // Malayalam
  if (/[\u0600-\u06FF]/.test(text)) return "ur-IN"; // Urdu/Arabic
  return "en-IN";
}

export default function AIConcierge() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([
    { role: "assistant", text: "Namaste! Main DestinoWay AI concierge. Bataiye, kahaan jaana hai? (Hindi, English, Bengali, Tamil ya jo bhi comfortable ho — usi me baat karein.)" },
  ]);
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speakReplies, setSpeakReplies] = useState(true); // user preference toggle
  const [voices, setVoices] = useState([]);
  const recognition = useRef(null);
  const endRef = useRef(null);
  const voiceInputRef = useRef(false); // true if the next reply was triggered by voice

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, open]);

  // Load available voices (may arrive async)
  useEffect(() => {
    if (!("speechSynthesis" in window)) return;
    const load = () => setVoices(window.speechSynthesis.getVoices() || []);
    load();
    window.speechSynthesis.onvoiceschanged = load;
    return () => { window.speechSynthesis.onvoiceschanged = null; };
  }, []);

  const speak = (reply) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(reply);
    const lang = detectLang(reply);
    const voice = pickVoice(voices, lang);
    if (voice) u.voice = voice;
    u.lang = voice?.lang || lang;
    u.rate = 1.0;
    u.pitch = 1.02;
    u.volume = 1;
    window.speechSynthesis.speak(u);
  };

  const send = async (preset, viaVoice = false) => {
    const t = (preset || text).trim();
    if (!t) return;
    setText("");
    voiceInputRef.current = viaVoice;
    setMessages((old) => [...old, { role: "user", text: t }, { role: "assistant", text: "", streaming: true }]);
    try {
      const resp = await fetch(`${API}/chat/stream`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: t, language: "auto", context: {} }),
      });
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = ""; let answer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const chunks = buffer.split("\n\n");
        buffer = chunks.pop();
        chunks.forEach((chunk) => {
          const line = chunk.split("\n").find((x) => x.startsWith("data: "));
          if (!line) return;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.text) {
              answer += ev.text;
              setMessages((old) => [...old.slice(0, -1), { role: "assistant", text: answer }]);
            }
          } catch { /* ignore */ }
        });
      }
      // Only speak if user used voice AND they haven't muted replies
      if (answer && voiceInputRef.current && speakReplies) {
        speak(answer);
      }
    } catch {
      setMessages((old) => [...old.slice(0, -1), { role: "assistant", text: "Concierge se connect nahi ho pa raha. Thodi der me try karein." }]);
    } finally {
      voiceInputRef.current = false;
    }
  };

  const toggleVoice = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { alert("Browser me voice input available nahi hai. Chrome/Edge try karein."); return; }
    if (listening) { recognition.current?.stop(); setListening(false); return; }
    // stop any ongoing speech first
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    const r = new SR();
    r.lang = "hi-IN"; // Hindi recognition also handles English + Hinglish well on Chrome
    r.interimResults = false;
    r.maxAlternatives = 1;
    r.onresult = (e) => {
      const said = e.results[0][0].transcript;
      setText(said);
      send(said, true); // mark as voice-triggered so reply is spoken
    };
    r.onerror = () => setListening(false);
    r.onend = () => setListening(false);
    recognition.current = r;
    try { r.start(); setListening(true); } catch { setListening(false); }
  };

  const toggleMute = () => {
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    setSpeakReplies((s) => !s);
  };

  if (!open) {
    return (
      <button className="concierge-fab" onClick={() => setOpen(true)} data-testid="concierge-open" aria-label="Open AI travel concierge">
        <Sparkles size={22}/>
      </button>
    );
  }

  return (
    <div className="concierge-panel" data-testid="concierge-panel">
      <div className="concierge-head">
        <div className="concierge-title">
          <span style={{width:36,height:36,background:'var(--teal)',color:'#06131a',borderRadius:'50%',display:'grid',placeItems:'center'}}><Sparkles size={16}/></span>
          <div>
            <strong>DestinoWay AI</strong>
            <small>MULTILINGUAL CONCIERGE</small>
          </div>
        </div>
        <div style={{display:'flex',gap:6,alignItems:'center'}}>
          <button
            className="icon-btn"
            onClick={toggleMute}
            data-testid="concierge-mute"
            title={speakReplies ? "Mute voice replies" : "Enable voice replies (on voice input)"}
            style={{width:34,height:34}}
          >
            {speakReplies ? <Volume2 size={14}/> : <VolumeX size={14}/>}
          </button>
          <button className="concierge-close" onClick={() => setOpen(false)} data-testid="concierge-close"><X size={20}/></button>
        </div>
      </div>
      <div className="chat-messages" data-testid="chat-messages">
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            <div className="chat-avatar">{m.role === "assistant" ? <Sparkles size={13}/> : "You"}</div>
            <div className="bubble" data-testid={`chat-message-${i}`}>{m.text || "…"}</div>
          </div>
        ))}
        <div ref={endRef}/>
      </div>
      {messages.length <= 2 && (
        <div className="chat-suggestions">
          {SUGGESTIONS.map((s, i) => (
            <button key={i} onClick={() => send(s, false)} data-testid={`suggestion-${i}`}>{s}</button>
          ))}
        </div>
      )}
      <div className="chat-compose">
        <button className={listening ? "icon-btn listening" : "icon-btn"} onClick={toggleVoice} data-testid="voice-input-button" aria-label="Voice input" title="Hold or tap to speak"><Mic size={16}/></button>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(null, false)}
          placeholder="Type here or tap mic to speak…"
          data-testid="chat-input"
        />
        <button className="icon-btn primary" onClick={() => send(null, false)} data-testid="send-chat-button" aria-label="Send"><Send size={16}/></button>
      </div>
      <div style={{padding:'0 20px 14px',color:'var(--muted)',fontSize:11,display:'flex',alignItems:'center',gap:6,lineHeight:1.5}}>
        <Volume2 size={12}/> Voice input → voice reply. Typing → text reply only. {speakReplies ? "" : "(voice muted)"}
      </div>
    </div>
  );
}
