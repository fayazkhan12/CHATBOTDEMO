import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createVoiceEngine, VOICE_LANGS, shouldSendUtterance, describeStop, pickDefaultLang, saveLang } from "../lib/voice";
import { resolvePick, hasPickIntent, isStrongReserve } from "../lib/voicecmd";
import { markVoiceFlow } from "../lib/voicedock";
import { useNavigate } from "react-router-dom";
import { Mic, Send, Sparkles, Plane, Hotel, BusFront, Car, Volume2, VolumeX, ArrowRight, RotateCcw, Bike, MapPin } from "lucide-react";
import { toast } from "sonner";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useChat, sendMessage, loadMore as storeLoadMore, retrySearch, clearChat, undoClear, setOwner, noteSelection, selectionFromItem, visibleCards } from "../lib/chatstore";
import { rideUrl } from "../lib/rides";
import { speak, stopSpeaking as cancelSpeech } from "../lib/tts";

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

// What the chat says under its reply while a search is running, and when the search finds nothing
const SEARCH_LABELS = {
  en: {
    wait: (service) => (service === "hotels" ? "Checking live hotel prices. This can take up to a minute." : "Finding the best options..."),
    none: "No options found for these dates and place. Try other dates or another city.",
  },
  hinglish: {
    wait: (service) => (service === "hotels" ? "Live hotel prices check ho rahe hain. Ek minute tak lag sakta hai." : "Sabse achhe options dhoondh rahe hain..."),
    none: "In dates aur jagah ke liye koi option nahi mila. Doosri date ya doosra shehar try karo.",
  },
  hi: {
    wait: (service) => (service === "hotels" ? "\u0932\u093e\u0907\u0935 \u0939\u094b\u091f\u0932 \u0915\u0940 \u0915\u0940\u092e\u0924\u0947\u0902 \u0926\u0947\u0916\u0940 \u091c\u093e \u0930\u0939\u0940 \u0939\u0948\u0902\u0964 \u090f\u0915 \u092e\u093f\u0928\u091f \u0924\u0915 \u0932\u0917 \u0938\u0915\u0924\u093e \u0939\u0948\u0964" : "\u0938\u092c\u0938\u0947 \u0905\u091a\u094d\u091b\u0947 \u0935\u093f\u0915\u0932\u094d\u092a \u0922\u0942\u0901\u0922 \u0930\u0939\u0947 \u0939\u0948\u0902..."),
    none: "\u0907\u0928 \u0924\u093e\u0930\u0940\u0916\u094b\u0902 \u0914\u0930 \u091c\u0917\u0939 \u0915\u0947 \u0932\u093f\u090f \u0915\u094b\u0908 \u0935\u093f\u0915\u0932\u094d\u092a \u0928\u0939\u0940\u0902 \u092e\u093f\u0932\u093e\u0964 \u0926\u0942\u0938\u0930\u0940 \u0924\u093e\u0930\u0940\u0916 \u092f\u093e \u0926\u0942\u0938\u0930\u093e \u0936\u0939\u0930 \u0906\u091c\u093c\u092e\u093e\u090f\u0901\u0964",
  },
};

const QUICK_STARTERS = [
  { label: "Hotels in Jaipur", icon: Hotel },
  { label: "Delhi to Goa flight", icon: Plane },
  { label: "Mumbai to Pune bus", icon: BusFront },
  { label: "Bike ride in Jaipur", icon: Bike },
  { label: "Airport cab Bangalore", icon: Car },
];

const INR = (n) => `₹${Math.round(Number(n) || 0).toLocaleString("en-IN")}`;

// The fares for a ride the visitor asked for in the chat. Tapping a vehicle opens the ride screen with it chosen.
function RideQuote({ ride, onOpen }) {
  const shown = ride.options.filter((o) => o.available);
  const wanted = ride.vehicle && ride.vehicle !== "any" ? ride.vehicle : "";
  const list = (wanted
    ? shown.filter((o) => (wanted === "cab" ? ["mini", "sedan", "suv"].includes(o.key) : o.key === wanted))
    : shown
  ).slice(0, 5);
  const rows = list.length ? list : shown.slice(0, 5);
  return (
    <div className="ride-quote" data-testid="chat-ride-quote">
      <div className="ride-quote-route">
        <MapPin size={14} />
        <span title={ride.pickup.name}>{ride.pickup.name}</span>
        <ArrowRight size={13} />
        <span title={ride.drop.name}>{ride.drop.name}</span>
      </div>
      <small className="ride-quote-meta">{ride.distance_km} km · about {ride.duration_min} min{ride.surge ? ` · ${ride.surge.label}` : ""}{ride.when && ride.when !== "now" ? " · scheduled" : ""}</small>
      {rows.length === 0 && <small>No vehicle is available for this trip. Try a closer drop place.</small>}
      {rows.map((o) => (
        <button key={o.key} className="ride-quote-row" onClick={() => onOpen(o.key)} data-testid={`chat-ride-${o.key}`}>
          <span className="ride-quote-name">{o.name}<small>{o.eta_min} min away · {o.seats} seat{o.seats > 1 ? "s" : ""}</small></span>
          <strong>{INR(o.fare)}</strong>
        </button>
      ))}
      <small className="ride-quote-note">Demo ride: no real driver is sent.</small>
      <button className="inline-cta" onClick={() => onOpen(wanted && rows[0] ? rows[0].key : "")} data-testid="chat-ride-open">Choose and book <ArrowRight size={12} /></button>
    </div>
  );
}

const MessageBubble = ({ msg, onOpenCard, onMore, onOpenRide, onRetry }) => (
  <div className={`chat-row ${msg.role}`} data-testid={`chat-row-${msg.role}`}>
    <div className="chat-avatar-lg">
      {msg.role === "assistant" ? <Sparkles size={16} /> : <span>You</span>}
    </div>
    <div className="chat-bubble-wrap">
      <div className="chat-bubble-lg">
        {msg.text || <span className="typing-dots"><i/><i/><i/></span>}
      </div>
      {msg.searching && (
        <div className="chat-status" role="status" data-testid="chat-searching">
          <span className="typing-dots"><i/><i/><i/></span>
          <small>{(SEARCH_LABELS[msg.lang] || SEARCH_LABELS.en).wait(msg.searching)}</small>
        </div>
      )}
      {msg.interrupted && !msg.searching && !msg.cards?.length && !msg.ride && (
        <div className="chat-status" data-testid="chat-interrupted">
          <small>This search was interrupted.</small>
          <button className="inline-cta" onClick={() => onRetry(msg)} data-testid="chat-search-again"><RotateCcw size={12}/> Search again</button>
        </div>
      )}
      {msg.cardsDropped && !msg.cards?.length && msg.search && (
        <div className="chat-status" data-testid="chat-cards-dropped">
          <small>Old results are not stored. </small>
          <button className="inline-cta" onClick={() => onRetry(msg)}><RotateCcw size={12}/> Show again</button>
        </div>
      )}
      {msg.noResults && (
        <div className="chat-status" data-testid="chat-no-results">
          <small>{msg.note || (SEARCH_LABELS[msg.lang] || SEARCH_LABELS.en).none}</small>
        </div>
      )}
      {msg.ride && <RideQuote ride={msg.ride} onOpen={(vehicle) => onOpenRide(msg.ride, vehicle)} />}
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

const MAX_AUTO_TURNS = 8;   // after this many questions answered by voice in a row, the visitor taps the mic again

// Does the assistant's reply end by asking the visitor something?
const asksQuestion = (text) => /[?\uFF1F]$/.test(String(text || "").trim().replace(/[)"'\u201d\]]+$/, ""));

export default function Home() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const chat = useChat();
  const messages = chat.messages;
  const sending = chat.sending;
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [speakingReply, setSpeakingReply] = useState(false);
  const [voiceOutput, setVoiceOutput] = useState(true);
  const endRef = useRef(null);
  const firstScroll = useRef(true);
  const voiceModeRef = useRef(false); // true for current send if invoked via mic
  const openCardRef = useRef(null);
  const voiceSessionRef = useRef(false);   // the visitor started voice mode and has not stopped it
  const autoTurnsRef = useRef(0);          // how many times the mic opened by itself after a question
  const speakIdRef = useRef(0);            // only the newest spoken reply may open the mic again
  const startListeningRef = useRef(null);
  const voiceLangRef = useRef("en-IN");

  // the chat belongs to one person: a different account (or logging out) starts a clean chat.
  // Wait until we know who is logged in, or a reload would look like a logout.
  useEffect(() => {
    if (authLoading) return;
    setOwner(user ? (user.user_id || user.email || "user") : "guest");
  }, [user, authLoading]);

  // warm up voices list on mount
  useEffect(() => { window.speechSynthesis?.getVoices(); }, []);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: firstScroll.current ? "auto" : "smooth" });
    firstScroll.current = false;
  }, [messages]);

  const openCard = (card) => {
    http.post("/travel/cache", [card]).catch(() => {});
    const service = card.type === "flight" ? "flights" : card.type === "hotel" ? "hotels" : card.type === "bus" ? "buses" : "cabs";
    noteSelection(selectionFromItem(card, "viewed"));
    navigate(`/detail/${service}/${encodeURIComponent(card.id)}`);
  };

  openCardRef.current = openCard;

  const openRide = (ride, vehicle) => navigate(rideUrl({ pickup: ride.pickup, drop: ride.drop, vehicle, when: ride.when }));

  const loadMore = (msg) => storeLoadMore(msg.id);
  const retry = (msg) => retrySearch(msg.id);

  const newChat = () => {
    speakIdRef.current += 1;
    voiceSessionRef.current = false;
    cancelSpeech();
    if (clearChat()) {
      toast("New chat started", { action: { label: "Undo", onClick: () => undoClear() }, duration: 6000 });
    }
  };

  const send = useCallback(async (preset, { fromVoice = false } = {}) => {
    const t = (preset ?? text).trim();
    if (!t || sending) return;
    voiceModeRef.current = fromVoice;
    setText("");
    const out = await sendMessage(t, { userName: user?.name || null });
    if (out && out.pick) {          // "open the second one", typed
      openCardRef.current(out.pick);
      voiceModeRef.current = false;
      return;
    }
    const clean = out ? out.clean : "";
    if (voiceModeRef.current && voiceOutput && clean) {
      const id = speakIdRef.current + 1;
      speakIdRef.current = id;
      setSpeakingReply(true);
      speak(clean, {
        preferred: voiceLangRef.current,
        onEnd: (spoken) => {
          if (id !== speakIdRef.current) return;      // a newer reply, the Stop button or the mic took over
          setSpeakingReply(false);
          if (spoken && voiceSessionRef.current && asksQuestion(clean)) listenAgain();
        },
      });
    }
    voiceModeRef.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text, sending, user, voiceOutput]);

  // ---- hands-free voice mode ----
  const [voiceLang, setVoiceLang] = useState(pickDefaultLang);
  voiceLangRef.current = voiceLang;
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
  lastCardsRef.current = visibleCards(messages);

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
    if (reason !== "done") { pendingVoice.current = ""; voiceSessionRef.current = false; }   // silence, errors and the stop button end voice mode
    setListening(false);
    setInterim("");
    if (reason !== "done") setVoiceNote(reason ? describeStop(reason) : "");
  }, []);

  const startListening = useCallback(() => {
    setVoiceNote("");
    const eng = createVoiceEngine({
      lang: voiceLangRef.current,
      onInterim: setInterim,
      onFinal: onVoiceFinal,
      onStop: stopVoice,
      once: true,
      idleMs: 12000,
    });
    if (!eng) { voiceSessionRef.current = false; setVoiceNote(describeStop("unsupported")); return; }
    voiceRef.current = eng;
    eng.start();
    setListening(true);
  }, [onVoiceFinal, stopVoice]);
  startListeningRef.current = startListening;

  // The assistant just asked something by voice and finished speaking: open the mic for the answer.
  const listenAgain = useCallback(() => {
    if (!voiceSessionRef.current || voiceRef.current) return;
    if (autoTurnsRef.current >= MAX_AUTO_TURNS) { voiceSessionRef.current = false; return; }
    autoTurnsRef.current += 1;
    setTimeout(() => {      // a short pause, so the end of the spoken question is not heard as the answer
      if (voiceSessionRef.current && !voiceRef.current && !sendingRef.current && startListeningRef.current) startListeningRef.current();
    }, 450);
  }, []);

  const toggleVoice = () => {
    if (listening) { voiceSessionRef.current = false; stopVoice(); return; }
    cancelSpeech();                       // tapping the mic while the assistant talks: it stops and listens
    speakIdRef.current += 1;
    setSpeakingReply(false);
    voiceSessionRef.current = true;
    autoTurnsRef.current = 0;
    startListening();
  };

  const changeVoiceLang = (code) => {
    setVoiceLang(code);
    voiceLangRef.current = code;
    saveLang(code);
    if (voiceRef.current) voiceRef.current.setLang(code);
  };

  // do not listen while the bot is speaking (it would hear itself)
  useEffect(() => {
    if (voiceRef.current) voiceRef.current.setPaused(speakingReply);
  }, [speakingReply]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => () => { voiceSessionRef.current = false; speakIdRef.current += 1; cancelSpeech(); if (voiceRef.current) voiceRef.current.destroy(); }, []);

  const stopSpeaking = () => {
    speakIdRef.current += 1;              // the reply that was being spoken must not open the mic when it is cut short
    voiceSessionRef.current = false;
    cancelSpeech();
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
          {messages.length > 1 && (
            <button className="icon-btn" onClick={newChat} title="Start a new chat" data-testid="new-chat">
              <RotateCcw size={15}/> <span className="new-chat-label">New chat</span>
            </button>
          )}
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
          <MessageBubble key={m.id} msg={m} onOpenCard={openCard} onMore={loadMore} onOpenRide={openRide} onRetry={retry}/>
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
          <span className="voice-dot" /> Listening... speak now. Tap the mic to stop.
        </div>
      )}
      {voiceNote && <div className="voice-note" role="status">{voiceNote}</div>}

    </div>
  );
}
