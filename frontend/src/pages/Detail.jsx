import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { useVoiceDock, markVoiceFlow, takeReserveFlow } from "../lib/useVoiceDock";
import { isReserveIntent, isBackIntent } from "../lib/voicecmd";
import { ArrowLeft, Check, Clock3, MapPin, Star, Users, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, shortDate, clockTime, dateRange, plural } from "../lib/format";

// hotel ids on the website look like ak-<supplierHotelId>
function hotelIdOf(item) {
  if (!item) return "";
  if (item.hotel_id) return String(item.hotel_id);
  const id = String(item.id || "");
  return id.startsWith("ak-") ? id.slice(3) : "";
}

const TRIP_TITLE = { flight: "Flight details", bus: "Bus details", cab: "Ride details" };

export default function Detail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
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

  // opened from a shared link or a new tab? then there is no page to go back to
  const goBack = () => {
    if (location.key !== "default") navigate(-1);
    else navigate("/");
  };

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

  // on a phone the reserve bar sits at the bottom, so the floating mic must sit above it
  const hasItem = !!item;
  useEffect(() => {
    if (!hasItem) return undefined;
    document.body.classList.add("has-reserve-bar");
    return () => document.body.classList.remove("has-reserve-bar");
  }, [hasItem]);

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
      if (isBackIntent(said)) { goBack(); return { listen: false }; }
      if (isReserveIntent(said)) { markVoiceFlow(); book(); return { say: "Reserving this for you.", listen: false }; }
      return { say: 'Sorry. Say "reserve now" or "back".', listen: true };
    },
  });

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading details&hellip;</div>;

  if (!item) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Option not found. <button className="btn-primary" onClick={goBack} style={{marginTop:14}}>Go back</button></div>;

  const type = item.type || "hotel";
  const isHotel = type === "hotel";
  const isDemo = item.mode !== "LIVE";
  const isLiveHotel = isHotel && !isDemo;

  const amenities = isHotel
    ? ((content && content.amenities && content.amenities.length) ? content.amenities : (item.amenities || []))
    : (item.meta || []);
  const nights = Number(item.nights) || (live && Number(live.nights)) || 0;
  const guests = Number(item.guests) || 0;
  const shownPrice = room ? room.price.payable : Math.round(Number(item.price) || 0);
  const hero = photos.length ? photos[Math.min(photo, photos.length - 1)] : null;
  const reserveLabel = booking ? "Preparing…" : liveState === "loading" ? "Loading rooms…" : "Reserve now";
  const reserveOff = booking || liveState === "loading" || liveState === "expired";

  const address = (content && content.address) || item.location;
  const hasGuestRating = !!(content && content.rating && Number(content.rating.value) > 0);
  const ratingValue = hasGuestRating ? Number(content.rating.value) : Number(item.rating) || 0;
  const ratingCount = hasGuestRating ? Number(content.rating.count) || 0 : 0;

  // hotels: the stay; flights, buses and cabs: the travel day
  const tripDay = shortDate(item.check_in || item.departure);
  const stay = isHotel ? dateRange(item.check_in, item.check_out) : tripDay;
  const priceNote = isHotel && nights ? `${plural(nights, "night")} total` : "per booking";

  // flight / bus / cab summary
  const dep = clockTime(item.departure);
  const arr = clockTime(item.arrival);
  const stops = item.stops;
  const stopsLabel = stops === undefined || stops === null ? "" : stops === 0 ? "Non-stop" : plural(Number(stops), "stop");
  const facts = [["Date", tripDay], ["Cabin", item.cabin], ["Baggage", item.baggage]].filter((f) => f[1]);

  let policy;
  if (room) policy = `${room.cancellation}. Please check the exact terms before you pay.`;
  else if (isDemo) policy = "This is a demo listing, so no real cancellation terms apply.";
  else if ((item.meta || []).includes("Free cancellation")) policy = "The supplier lists free cancellation on this rate. Please check the exact terms before you pay.";
  else policy = "Cancellation terms depend on the rate you choose. Please check them before you pay.";

  const showNotes = !!content && (!!content.check_in_from || !!content.check_out_by || (content.notes && content.notes.length > 0));

  return (
    <div className="detail-page" data-testid="detail-page">
      <button className="btn-ghost" onClick={goBack} style={{marginBottom:20}} data-testid="back-btn"><ArrowLeft size={14}/> Back</button>
      {hero && (
        <div className={isHotel ? "detail-hero" : "detail-hero dl-hero-flat"}>
          <img src={hero.url} alt={isHotel ? (hero.caption || item.title) : ""} onError={() => setBrokenPhotos((b) => ({ ...b, [hero.url]: true }))}/>
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
          <span className={isDemo ? "badge-demo" : "badge-live"}>{isDemo ? "DEMO" : "LIVE"}</span>
          <h1 data-testid="detail-title">{item.title}</h1>
          <div className="detail-brand">{item.brand}</div>
          <div className="dl-meta">
            {address && <span><MapPin size={14}/> {address}</span>}
            {ratingValue > 0 && (
              <span data-testid="detail-rating">
                <Star size={14} style={{color:'var(--gold)',fill:'var(--gold)'}}/> {ratingValue} rating
                {ratingCount > 0 ? ` (${plural(ratingCount, "review")})` : ""}
              </span>
            )}
            {item.duration && <span><Clock3 size={14}/> {item.duration}</span>}
          </div>

          {isDemo && (
            <div className="dl-note dl-demo" role="note" data-testid="demo-note">
              Demo listing. This is sample data to show how booking works. No real ticket is issued and no real money is charged.
            </div>
          )}

          {isHotel && (
            <p style={{color:'var(--muted)',lineHeight:1.7}} data-testid="detail-about">
              {content && content.description ? content.description : `${item.title}${item.brand ? ` — ${item.brand}` : ""}.`}
            </p>
          )}

          {!isHotel && (
            <div className="detail-section" data-testid="trip-section">
              <h3>{TRIP_TITLE[type] || "Trip details"}</h3>
              <div className="dl-trip">
                <div className="dl-leg">
                  <div className="dl-stop">
                    <strong>{dep || item.origin}</strong>
                    <span>{dep ? item.origin : "Pickup"}</span>
                  </div>
                  <div className="dl-leg-mid" aria-hidden="true">
                    {item.duration ? <small>{item.duration}</small> : null}
                    <i/>
                    {stopsLabel ? <small>{stopsLabel}</small> : null}
                  </div>
                  <div className="dl-stop dl-stop-end">
                    <strong>{arr || item.destination}</strong>
                    <span>{arr ? item.destination : "Drop"}</span>
                    {dep && arr && arr < dep ? <em>next day</em> : null}
                  </div>
                </div>
                {facts.length > 0 && (
                  <dl className="dl-facts">
                    {facts.map((f) => <div key={f[0]}><dt>{f[0]}</dt><dd>{f[1]}</dd></div>)}
                  </dl>
                )}
              </div>
            </div>
          )}

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
                  const extras = (r.amenities || []).slice(0, 4).join(" · ");
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
                        <small>{plural(nights || 1, "night")} total</small>
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

          {amenities.length > 0 && (
            <div className="detail-section">
              <h3>{isHotel && content ? "Hotel amenities" : "What's included"}</h3>
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
            <p style={{color:'var(--muted)',fontSize:13,lineHeight:1.6}} data-testid="detail-policy">{policy}</p>
          </div>

          {showNotes && (
            <details className="dl-notes" data-testid="hotel-notes">
              <summary>Check-in and hotel notes</summary>
              {content.check_in_from && <p>Check-in from {content.check_in_from}.</p>}
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
          {stay ? <div className="booking-row"><span className="dl-row-label"><CalendarDays size={13}/>{isHotel ? "Stay" : "Date"}</span><span>{stay}</span></div> : null}
          {isHotel && nights > 0 ? <div className="booking-row"><span>Length</span><span>{plural(nights, "night")}</span></div> : null}
          {guests > 0 ? <div className="booking-row"><span className="dl-row-label"><Users size={13}/>{isHotel ? "Guests" : "Travellers"}</span><span>{guests}</span></div> : null}
          <div className="booking-row"><span>Total</span><span>{money(shownPrice)}</span></div>
          <button
            className="btn-primary"
            style={{width:'100%',padding:'14px',marginTop:16,fontSize:15}}
            onClick={book}
            disabled={reserveOff}
            data-testid="book-now-btn"
          >
            {reserveLabel}
          </button>
          <p style={{color:'var(--muted)',fontSize:11,textAlign:'center',marginTop:10,lineHeight:1.5}}>
            {isDemo ? "Demo listing. No real payment is taken." : "You won't be charged until the next step. Razorpay-secured."}
          </p>
        </aside>
      </div>

      <div className="dl-mobile-bar" data-testid="mobile-reserve-bar">
        <div className="dl-mobile-price">
          <strong>{money(shownPrice)}</strong>
          <small>{priceNote}</small>
        </div>
        <button className="btn-primary" onClick={book} disabled={reserveOff} data-testid="book-now-mobile">{reserveLabel}</button>
      </div>
    </div>
  );
}
