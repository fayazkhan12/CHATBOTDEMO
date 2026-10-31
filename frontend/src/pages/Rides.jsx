import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams, Link } from "react-router-dom";
import { toast } from "sonner";
import { ArrowUpDown, Banknote, CalendarClock, ChevronRight, CreditCard, Info, Loader2, Zap } from "lucide-react";
import PlaceInput, { getPosition } from "../components/PlaceInput";
import VehicleIcon from "../components/VehicleIcon";
import { useAuth } from "../lib/auth";
import { boxLimits, boxToWhen, errorCode, errorText, fmtINR, hasPoint, readRideParams, rideApi, rideUrl, whenText, whenToBox } from "../lib/rides";

const RideMap = lazy(() => import("../components/RideMap"));

const EXAMPLES = [
  { a: "Jaipur Airport", b: "Hawa Mahal" },
  { a: "Delhi Railway Station", b: "Connaught Place" },
  { a: "Bengaluru Airport", b: "MG Road" },
];

// which cards match what the chat or a link asked for ("bike", "auto", "cab" or one vehicle)
const wishes = (wish, key) => !wish || wish === "any" || wish === key || (wish === "cab" && ["mini", "sedan", "suv"].includes(key));

export default function Rides() {
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [params, setParams] = useSearchParams();
  const first = useMemo(() => readRideParams(params), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [pickup, setPickup] = useState(first.pickup);
  const [drop, setDrop] = useState(first.drop);
  const [when, setWhen] = useState(first.when || "now");
  const [wish] = useState(first.vehicle);
  const [vehicle, setVehicle] = useState("");
  const [pay, setPay] = useState("cash");
  const [quote, setQuote] = useState(null);
  const [state, setState] = useState("idle");          // idle | loading | ok | error
  const [problem, setProblem] = useState("");
  const [booking, setBooking] = useState(false);
  const [active, setActive] = useState(null);
  const [locating, setLocating] = useState(false);
  const seq = useRef(0);
  const limits = useMemo(boxLimits, []);

  // pickup: use the current location right away when the visitor has already allowed it (never prompts)
  useEffect(() => {
    if (first.pickup || !navigator.permissions || !navigator.permissions.query) return;
    let live = true;
    navigator.permissions.query({ name: "geolocation" }).then((st) => {
      if (live && st.state === "granted") getPosition().then((p) => { if (live) setPickup((old) => old || p); }).catch(() => {});
    }).catch(() => {});
    return () => { live = false; };
  }, [first.pickup]);

  // a ride that is still going on
  useEffect(() => {
    if (authLoading || !user) { setActive(null); return; }
    let live = true;
    rideApi.active().then((r) => { if (live) setActive(r); }).catch(() => {});
    return () => { live = false; };
  }, [user, authLoading]);

  const readyForQuote = !!(pickup && drop && (pickup.query || pickup.name) && (drop.query || drop.name));

  const fetchQuote = useCallback(async (quiet = false) => {
    if (!pickup || !drop) return;
    const mine = ++seq.current;
    if (!quiet) { setState("loading"); setProblem(""); }
    try {
      const q = await rideApi.quote(pickup, drop, when);
      if (mine !== seq.current) return;
      setQuote(q);
      setState("ok");
      setProblem("");
      setVehicle((old) => {
        const ok = (k) => q.options.some((o) => o.key === k && o.available);
        if (old && ok(old)) return old;
        const pref = q.options.find((o) => o.available && wishes(wish, o.key));
        return (pref || q.options.find((o) => o.available) || {}).key || "";
      });
    } catch (e) {
      if (mine !== seq.current) return;
      setQuote(null);
      setState("error");
      setProblem(errorText(e, "Fares are not available right now. Please try again."));
    }
  }, [pickup, drop, when, wish]);

  useEffect(() => {
    if (!readyForQuote) { seq.current += 1; setQuote(null); setState("idle"); setProblem(""); return; }
    const t = setTimeout(() => fetchQuote(false), 200);
    return () => clearTimeout(t);
  }, [readyForQuote, fetchQuote]);

  // fares are good for 15 minutes: refresh a little before
  useEffect(() => {
    if (!quote) return;
    const t = setTimeout(() => fetchQuote(true), Math.max(60, quote.expires_in - 90) * 1000);
    return () => clearTimeout(t);
  }, [quote, fetchQuote]);

  // keep the address in step with the choice (reload and Back come back to the same screen)
  // (places typed as words are saved with the coordinates the server found for them)
  const urlPickup = hasPoint(pickup) || !quote ? pickup : quote.pickup;
  const urlDrop = hasPoint(drop) || !quote ? drop : quote.drop;
  useEffect(() => {
    const url = rideUrl({ pickup: urlPickup, drop: urlDrop, vehicle: vehicle || wish, when });
    const q = url.includes("?") ? url.slice(url.indexOf("?") + 1) : "";
    setParams(new URLSearchParams(q), { replace: true });
  }, [urlPickup, urlDrop, vehicle, wish, when, setParams]);

  const swap = () => { setPickup(drop); setDrop(pickup); };

  const here = async () => {
    setLocating(true);
    try { setPickup(await getPosition()); } catch (e) {
      toast.error(e && e.code === 1 ? "Location is blocked for this site. Allow it in your browser, or type the pickup place." : "Could not get your location. Type the pickup place instead.");
    } finally { setLocating(false); }
  };

  const chosen = quote && quote.options.find((o) => o.key === vehicle);

  const book = async () => {
    if (!quote || !chosen || booking) return;
    if (!user) {
      navigate(`/login?redirect=${encodeURIComponent(rideUrl({ pickup: urlPickup, drop: urlDrop, vehicle, when }))}`);
      return;
    }
    setBooking(true);
    try {
      const ride = await rideApi.book(quote.quote_token, vehicle, pay);
      navigate(`/ride/${ride.ride_id}`);
    } catch (e) {
      const d = errorCode(e);
      if (d.code === "active_ride" && d.ride_id) {
        toast.error(d.message);
        navigate(`/ride/${d.ride_id}`);
      } else if (d.code === "quote_expired") {
        toast("Fares were updated. Please check and book again.");
        fetchQuote(false);
      } else {
        toast.error(errorText(e, "Could not book the ride. Please try again."));
      }
    } finally {
      setBooking(false);
    }
  };

  const scheduled = when !== "now";
  const setSchedule = (on) => {
    if (!on) { setWhen("now"); return; }
    const d = new Date(Date.now() + 60 * 60000);
    d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
    const p = (n) => String(n).padStart(2, "0");
    setWhen(boxToWhen(`${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`));
  };

  const nearForSearch = hasPoint(drop) ? drop : hasPoint(pickup) ? pickup : null;

  return (
    <div className="rides-page" data-testid="rides-page">
      <section className="rides-map-col" aria-label="Map">
        <Suspense fallback={<div className="ride-map ride-map-loading"><Loader2 className="spin" size={20} /></div>}>
          <RideMap
            pickup={hasPoint(urlPickup) ? urlPickup : null}
            drop={hasPoint(urlDrop) ? urlDrop : null}
            route={quote ? quote.route : null}
            label="Pickup, drop and route"
          />
        </Suspense>
      </section>

      <section className="rides-panel">
        <h1 className="rides-title">Book a ride</h1>
        <p className="rides-sub">Bike, auto or cab. Pick the places, see the fare, go.</p>

        {active && (
          <Link to={`/ride/${active.ride_id}`} className="rides-active" data-testid="rides-active-banner">
            <Zap size={16} /> <span><b>You have a ride going on</b><small>{active.state.headline}</small></span><ChevronRight size={16} />
          </Link>
        )}

        <div className="rides-form">
          <PlaceInput label="Pickup" tone="pickup" value={pickup} onChange={setPickup} near={nearForSearch} allowCurrent placeholder="Where should we pick you up?" testid="pickup-input" />
          <button type="button" className="rides-swap" onClick={swap} aria-label="Swap pickup and drop" disabled={!pickup && !drop} data-testid="ride-swap"><ArrowUpDown size={16} /></button>
          <PlaceInput label="Drop" tone="drop" value={drop} onChange={setDrop} near={nearForSearch} placeholder="Where do you want to go?" testid="drop-input" />
        </div>
        {!pickup && (
          <button type="button" className="rides-here" onClick={here} disabled={locating} data-testid="ride-use-location">
            {locating ? <Loader2 className="spin" size={14} /> : <span className="rides-here-dot" />} Use my current location
          </button>
        )}

        <div className="rides-when" role="group" aria-label="When">
          <button type="button" className={!scheduled ? "seg on" : "seg"} onClick={() => setSchedule(false)} data-testid="ride-now">Now</button>
          <button type="button" className={scheduled ? "seg on" : "seg"} onClick={() => setSchedule(true)} data-testid="ride-later"><CalendarClock size={14} /> Schedule</button>
        </div>
        {scheduled && (
          <div className="rides-schedule">
            <label htmlFor="ride-when">Pickup time (India time)</label>
            <input id="ride-when" type="datetime-local" min={limits.min} max={limits.max} value={whenToBox(when)} onChange={(e) => e.target.value && setWhen(boxToWhen(e.target.value))} data-testid="ride-when" />
            <small>Book 20 minutes to 29 days ahead. A captain is found just before pickup.</small>
          </div>
        )}

        {state === "idle" && (
          <div className="rides-hint" data-testid="rides-hint">
            <p>Try a quick one:</p>
            <div className="rides-examples">
              {EXAMPLES.map((x) => (
                <button key={x.a} type="button" onClick={() => { setPickup({ name: x.a, query: x.a }); setDrop({ name: x.b, query: x.b }); }}>{x.a} <ChevronRight size={12} /> {x.b}</button>
              ))}
            </div>
          </div>
        )}

        {state === "loading" && (
          <div className="rides-loading" role="status" data-testid="rides-loading"><Loader2 className="spin" size={16} /> Checking fares and pickup times...</div>
        )}
        {state === "error" && problem && <div className="rides-problem" role="alert" data-testid="rides-problem">{problem}</div>}

        {quote && state !== "error" && (
          <div className={state === "loading" ? "rides-quote is-stale" : "rides-quote"} data-testid="rides-quote">
            <div className="rides-trip">
              <b>{quote.distance_km} km</b> · about <b>{quote.duration_min} min</b>
              {quote.scheduled && <span className="rides-chip"><CalendarClock size={12} /> {whenText(quote.when)}</span>}
            </div>
            {quote.surge && <div className="rides-surge" data-testid="rides-surge"><Zap size={13} /> {quote.surge.label}</div>}
            {quote.route_source === "estimate" && <div className="rides-note"><Info size={13} /> Road route is not available now, so distance is an estimate.</div>}
            <ul className="vehicle-list" role="radiogroup" aria-label="Choose a ride">
              {quote.options.map((o) => (
                <li key={o.key}>
                  <button type="button" role="radio" aria-checked={vehicle === o.key} disabled={!o.available}
                    className={`vehicle-card${vehicle === o.key ? " on" : ""}${!o.available ? " off" : ""}${wishes(wish, o.key) && wish ? " wished" : ""}`}
                    onClick={() => setVehicle(o.key)} data-testid={`vehicle-${o.key}`}>
                    <VehicleIcon kind={o.key} size={28} />
                    <span className="vehicle-info">
                      <b>{o.name}</b>
                      <small>{o.available ? `${o.eta_min} min away · ${o.seats} seat${o.seats > 1 ? "s" : ""} · ${o.tagline}` : o.reason}</small>
                    </span>
                    {o.available && <strong className="vehicle-fare">{fmtINR(o.fare)}</strong>}
                  </button>
                </li>
              ))}
            </ul>

            <div className="rides-pay" role="radiogroup" aria-label="Payment">
              <button type="button" role="radio" aria-checked={pay === "cash"} className={pay === "cash" ? "seg on" : "seg"} onClick={() => setPay("cash")} data-testid="pay-cash"><Banknote size={14} /> Cash</button>
              <button type="button" role="radio" aria-checked={pay === "online"} className={pay === "online" ? "seg on" : "seg"} onClick={() => setPay("online")} data-testid="pay-online"><CreditCard size={14} /> Online</button>
            </div>

            <button type="button" className="btn-primary rides-book" disabled={!chosen || booking} onClick={book} data-testid="ride-book">
              {booking ? <><Loader2 className="spin" size={16} /> Booking...</> : chosen ? `${quote.scheduled ? "Schedule" : "Book"} ${chosen.name} · ${fmtINR(chosen.fare)}` : "Choose a ride"}
            </button>
            {!user && chosen && <small className="rides-login-note">You will be asked to log in before booking.</small>}
            <small className="rides-demo" data-testid="rides-demo-note">{quote.demo_note} Fares are estimates including 5% GST.</small>
          </div>
        )}
      </section>
    </div>
  );
}
