import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useVoiceDock, markVoiceFlow, takeReserveFlow } from "../lib/useVoiceDock";
import { isReserveIntent, isBackIntent } from "../lib/voicecmd";
import { ArrowLeft, Check, Clock3, MapPin, Star, Users, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";

const RUPEE = "\u20b9";
const money = (n) => RUPEE + Math.round(Number(n) || 0).toLocaleString("en-IN");

// hotel ids on the website look like ak-<supplierHotelId>
function hotelIdOf(item) {
  if (!item) return "";
  if (item.hotel_id) return String(item.hotel_id);
  const id = String(item.id || "");
  return id.startsWith("ak-") ? id.slice(3) : "";
}

// "2026-11-10" -> "10 Nov"
function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
  if (!m) return "";
  const d = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])));
  return d.toLocaleDateString("en-IN", { day: "numeric", month: "short", timeZone: "UTC" });
}

export default function Detail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);
  // live hotel details (photos, amenities, rooms) from the company hotel API
  const [live, setLive] = useState(null);
  const [liveState, setLiveState] = useState("idle"); // idle | loading | ready | failed | expired
  const [pickedRoom, setPickedRoom] = useState(null);
  const [photo, setPhoto] = useState(0);
  const [brokenPhotos, setBrokenPhotos] = useState({});

  useEffect(() => {
    http.get(`/travel/detail/${encodeURIComponent(id)}`)
      .then(({ data }) => setItem(data))
      .catch(() => toast.error("This option is no longer available. Please search again."))
      .finally(() => setLoading(false));
  }, [id]);

  useEffect(() => {
    if (!item) return undefined;
    const hotelId = hotelIdOf(item);
    if ((item.type || "hotel") !== "hotel" || item.mode !== "LIVE" || !item.search_id || !hotelId) {
      setLiveState("failed");
      return undefined;
    }
    let stale = false;
    setLiveState("loading");
    http.get(`/hotels/live/${encodeURIComponent(item.search_id)}/${encodeURIComponent(hotelId)}`, {
      params: item.nights ? { nights: item.nights } : undefined,
      timeout: 45000,
    })
      .then(({ data }) => {
        if (stale) return;
        setLive(data);
        setLiveState((data.rooms && data.rooms.length) || data.content ? "ready" : "failed");
      })
      .catch((e) => {
        if (stale) return;
        setLiveState(e && e.response && e.response.status === 410 ? "expired" : "failed");
      });
    return () => { stale = true; };
  }, [item]);

  const content = live && live.content ? live.content : null;
  const rooms = live && Array.isArray(live.rooms) ? live.rooms : [];
  const room = rooms.find((r) => r.recommendation_id === pickedRoom) || rooms[0] || null;

  const photos = useMemo(() => {
    const out = [];
    const seen = new Set();
    const add = (url, caption) => {
      if (url && !seen.has(url) && !brokenPhotos[url]) {
        seen.add(url);
        out.push({ url, caption: caption || "" });
      }
    };
    ((live && live.content && live.content.images) || []).forEach((p) => add(p.url, p.caption));
    add(item && item.image, "");
    return out;
  }, [live, item, brokenPhotos]);

  const book = async () => {
    if (!user) {
      toast.info("Please log in to continue to checkout.");
      navigate(`/login?redirect=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    if (liveState === "expired") {
      toast.error("These live prices have expired. Please go back and search again.");
      return;
    }
    if (liveState === "loading") {
      toast.info("Loading the room options. One moment.");
      return;
    }
    setBooking(true);
    try {
      // when a live room is chosen, the booking carries that room and its own signed price
      const chosen = room && room.price_token
        ? {
            ...item,
            id: room.booking_id,
            title: `${item.title} - ${room.name}`,
            price: room.price.payable,
            price_token: room.price_token,
            recommendation_id: room.recommendation_id,
            room_name: room.name,
            cancellation: room.cancellation,
            board: room.board || "",
          }
        : item;
      const { data } = await http.post("/bookings", {
        item: chosen,
        traveller: { name: user.name, email: user.email, contact: user.contact || "" },
        amount_rupees: Math.round(chosen.price),
        service: item.type || "hotel",
      });
      navigate(`/checkout/${data.booking_id}`);
    } catch (e) {
      const why = e && e.response && e.response.data && e.response.data.detail;
      toast.error(typeof why === "string" ? why : "Could not start checkout. Try again.");
    } finally {
      setBooking(false);
    }
  };

  useEffect(() => {
    if (!item || liveState === "idle" || liveState === "loading") return;
    if (takeReserveFlow()) { markVoiceFlow(); book(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item, liveState]);

  useVoiceDock({
    maxTurns: 5,
    onStart: () => ({ say: 'Say "reserve now" to book this one, or "back" to see other options.', listen: true }),
    onText: (said) => {
      if (isBackIntent(said)) { navigate(-1); return { listen: false }; }
      if (isReserveIntent(said)) { markVoiceFlow(); book(); return { say: "Reserving this for you.", listen: false }; }
      return { say: 'Sorry. Say "reserve now" or "back".', listen: true };
    },
  });

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading details&hellip;</div>;

  if (!item) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Option not found. <button className="btn-primary" onClick={() => navigate(-1)} style={{marginTop:14}}>Go back</button></div>;

  const isLiveHotel = (item.type || "hotel") === "hotel" && item.mode === "LIVE";
  const amenities = (content && content.amenities && content.amenities.length)
    ? content.amenities
    : (item.amenities || (item.mode === "LIVE" ? [] : ["Breakfast included", "Free cancellation", "24\u00d77 concierge", "Wi-Fi"]));
  const nights = item.nights || (live && live.nights) || 1;
  const shownPrice = room ? room.price.payable : Math.round(Number(item.price) || 0);
  const hero = photos.length ? photos[Math.min(photo, photos.length - 1)] : null;
  const stay = item.check_in && item.check_out
    ? `${shortDate(item.check_in)} - ${shortDate(item.check_out)}`
    : `${nights} ${nights === 1 ? "night" : "nights"}`;
  const reserveLabel = booking ? "Preparing\u2026" : liveState === "loading" ? "Loading rooms\u2026" : "Reserve now";

  return (
    <div className="detail-page" data-testid="detail-page">
      <button className="btn-ghost" onClick={() => navigate(-1)} style={{marginBottom:20}} data-testid="back-btn"><ArrowLeft size={14}/> Back</button>
      {hero && (
        <div className="detail-hero">
          <img src={hero.url} alt={hero.caption || item.title} onError={() => setBrokenPhotos((b) => ({ ...b, [hero.url]: true }))}/>
        </div>
      )}
      {photos.length > 1 && (
        <div className="dl-thumbs" data-testid="photo-strip">
          {photos.slice(0, 12).map((p, i) => (
            <button
              type="button"
              key={p.url}
              className="dl-thumb"
              aria-label={`Show picture ${i + 1} of ${Math.min(photos.length, 12)}`}
              aria-current={i === Math.min(photo, photos.length - 1) ? "true" : undefined}
              onClick={() => setPhoto(i)}
            >
              <img src={p.url} alt="" loading="lazy" onError={() => setBrokenPhotos((b) => ({ ...b, [p.url]: true }))}/>
            </button>
          ))}
        </div>
      )}
      <div className="detail-grid">
        <div className="detail-body">
          <span className={item.mode === "LIVE" ? "badge-live" : "badge-demo"}>{item.mode}</span>
          <h1 data-testid="detail-title">{item.title}</h1>
          <div className="detail-brand">{item.brand}</div>
          <div style={{display:'flex',flexWrap:'wrap',gap:20,color:'var(--muted)',fontSize:14,marginBottom:20}}>
            {(content && content.address ? content.address : item.location) && <span><MapPin size={14} style={{marginRight:4,verticalAlign:'-2px'}}/> {content && content.address ? content.address : item.location}</span>}
            {item.rating && <span><Star size={14} style={{color:'var(--gold)',fill:'var(--gold)',marginRight:4,verticalAlign:'-2px'}}/> {item.rating} rating</span>}
            {item.duration && <span><Clock3 size={14} style={{marginRight:4,verticalAlign:'-2px'}}/> {item.duration}</span>}
          </div>
          <p style={{color:'var(--muted)',lineHeight:1.7}} data-testid="detail-about">
            {content && content.description ? content.description : `${item.title}${item.brand ? ` \u2014 ${item.brand}` : ""}.`}
          </p>

          {isLiveHotel && liveState === "loading" && (
            <div className="detail-section" data-testid="rooms-loading">
              <h3>Choose your room</h3>
              <div className="dl-skel" aria-busy="true"><span className="spinner"/> Loading live rooms and prices&hellip;</div>
            </div>
          )}
          {isLiveHotel && liveState === "expired" && (
            <div className="detail-section dl-note" role="alert" data-testid="rooms-expired">
              These live prices have expired. Please go back and search again to see the latest rooms and rates.
            </div>
          )}
          {isLiveHotel && liveState === "failed" && (
            <div className="detail-section dl-note" data-testid="rooms-failed">
              Room options are not available right now. You can still reserve at the listed price.
            </div>
          )}

          {rooms.length > 0 && (
            <div className="detail-section" data-testid="rooms-section">
              <h3>Choose your room</h3>
              <div className="dl-rooms" role="radiogroup" aria-label="Room options">
                {rooms.map((r) => {
                  const on = !!room && r.recommendation_id === room.recommendation_id;
                  const extras = (r.amenities || []).slice(0, 4).join(" \u00b7 ");
                  return (
                    <label key={r.recommendation_id} className={`dl-room${on ? " is-on" : ""}`} data-testid="room-option">
                      <input
                        type="radio"
                        name="room"
                        className="dl-radio"
                        checked={on}
                        onChange={() => setPickedRoom(r.recommendation_id)}
                      />
                      {r.images && r.images[0]
                        ? <img className="dl-room-img" src={r.images[0]} alt="" loading="lazy"/>
                        : <span className="dl-room-img dl-room-noimg" aria-hidden="true"/>}
                      <span className="dl-room-main">
                        <strong className="dl-room-name">{r.name}</strong>
                        {r.beds && <span className="dl-room-sub">{r.beds}</span>}
                        {extras && <span className="dl-room-sub">{extras}</span>}
                        <span className="dl-chips">
                          {r.board && <span className="dl-chip">{r.breakfast_included ? "Breakfast included" : r.board}</span>}
                          <span className={`dl-chip${r.free_cancellation_until ? " dl-chip-good" : r.refundable ? "" : " dl-chip-warn"}`}>{r.cancellation}</span>
                          {r.rooms_left ? <span className="dl-chip dl-chip-warn">Only {r.rooms_left} left</span> : null}
                          {r.pay_at_hotel ? <span className="dl-chip">Pay at hotel</span> : null}
                        </span>
                      </span>
                      <span className="dl-room-price">
                        {r.price.before_coupon ? <s>{money(r.price.before_coupon)}</s> : null}
                        <strong>{money(r.price.payable)}</strong>
                        <small>{nights} {nights === 1 ? "night" : "nights"} total</small>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {amenities.length > 0 && (
            <div className="detail-section">
              <h3>{content ? "Hotel amenities" : "What's included"}</h3>
              <div className="amen-grid">
                {amenities.map(a => <span key={a}><Check size={14} style={{color:'var(--teal)'}}/> {a}</span>)}
              </div>
            </div>
          )}

          {content && content.nearby && content.nearby.length > 0 && (
            <div className="detail-section" data-testid="nearby-section">
              <h3>What&apos;s nearby</h3>
              <ul className="dl-near">
                {content.nearby.map((p) => (
                  <li key={p.name}><span>{p.name}</span><span>{p.distance_km === null || p.distance_km === undefined ? "" : `${p.distance_km} km`}</span></li>
                ))}
              </ul>
            </div>
          )}

          <div className="detail-section">
            <h3>Cancellation policy</h3>
            <p style={{color:'var(--muted)',fontSize:13,lineHeight:1.6}}>
              {room
                ? `${room.cancellation}. Please check the exact terms before you pay.`
                : (item.meta || []).includes('Free cancellation')
                  ? 'The supplier lists free cancellation on this rate. Please check the exact terms before you pay.'
                  : 'Cancellation terms depend on the rate you choose. Please check them before you pay.'}
            </p>
          </div>

          {content && ((content.notes && content.notes.length > 0) || content.check_out_by) && (
            <details className="dl-notes" data-testid="hotel-notes">
              <summary>Check-in and hotel notes</summary>
              {content.check_out_by && <p>Check-out by {content.check_out_by}.</p>}
              {(content.notes || []).map((n) => <p key={n}>{n}</p>)}
            </details>
          )}
        </div>

        <aside className="booking-sticky" data-testid="booking-card">
          <h4>Total price</h4>
          <div className="booking-price" data-testid="booking-price">{money(shownPrice)}</div>
          <div style={{color:'var(--muted)',fontSize:12,marginBottom:16}}>Taxes &amp; fees included &middot; {item.currency}</div>
          {room && room.price.before_coupon ? <div className="dl-save" data-testid="booking-save">You save {money(room.price.savings)} (was {money(room.price.before_coupon)})</div> : null}
          {room && <div className="booking-row"><span>Room</span><span className="dl-row-val">{room.name}</span></div>}
          <div className="booking-row"><span><CalendarDays size={13} style={{marginRight:6,verticalAlign:'-2px'}}/>Stay / Trip</span><span>{stay}</span></div>
          <div className="booking-row"><span><Users size={13} style={{marginRight:6,verticalAlign:'-2px'}}/>Travellers</span><span>{item.guests || 2} guests</span></div>
          <div className="booking-row"><span>Service fee</span><span>Included</span></div>
          <div className="booking-row"><span>Total</span><span>{money(shownPrice)}</span></div>
          <button
            className="btn-primary"
            style={{width:'100%',padding:'14px',marginTop:16,fontSize:15}}
            onClick={book}
            disabled={booking || liveState === "loading" || liveState === "expired"}
            data-testid="book-now-btn"
          >
            {reserveLabel}
          </button>
          <p style={{color:'var(--muted)',fontSize:11,textAlign:'center',marginTop:10,lineHeight:1.5}}>
            You won't be charged until the next step. Razorpay-secured.
          </p>
        </aside>
      </div>
    </div>
  );
}
