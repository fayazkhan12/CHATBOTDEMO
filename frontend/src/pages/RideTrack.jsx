import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Banknote, Check, ChevronRight, CreditCard, FileText, Loader2, MessageCircle, Phone, RotateCcw, Share2, ShieldCheck, Star, X } from "lucide-react";
import VehicleIcon from "../components/VehicleIcon";
import { useAuth } from "../lib/auth";
import { loadRazorpay } from "../lib/api";
import { errorText, fmtINR, initials, isActiveStage, rideApi, rideUrl, STAGE_TITLE, whenText } from "../lib/rides";

const RideMap = lazy(() => import("../components/RideMap"));

const TIPS = [0, 10, 20, 30];
const GOOD_TAGS = ["Polite captain", "Smooth ride", "Safe driving", "On time", "Clean vehicle", "Good navigation"];
const BAD_TAGS = ["Rash driving", "Late arrival", "Rude behaviour", "Vehicle not clean"];

function Pulse() {
  return <span className="ride-pulse" aria-hidden="true"><i /><i /><i /></span>;
}

function Otp({ code }) {
  return (
    <div className="ride-otp" data-testid="ride-otp">
      <small>Tell this OTP to your captain to start the ride</small>
      <div className="ride-otp-digits" aria-label={`OTP ${String(code).split("").join(" ")}`}>
        {String(code).split("").map((d, i) => <span key={i}>{d}</span>)}
      </div>
    </div>
  );
}

function Captain({ ride }) {
  const c = ride.state.captain;
  if (!c) return null;
  return (
    <div className="ride-captain" data-testid="ride-captain">
      <span className="ride-avatar" aria-hidden="true">{initials(c.name)}</span>
      <span className="ride-captain-info">
        <b>{c.name}</b>
        <small><Star size={12} className="star-on" /> {c.rating} · {c.trips.toLocaleString("en-IN")} rides</small>
        <small>{c.vehicle_color} {c.vehicle_model}</small>
      </span>
      <span className="ride-plate" data-testid="ride-plate">{c.plate}</span>
    </div>
  );
}

function Route({ ride }) {
  return (
    <ol className="ride-route-list">
      <li><span className="dot pickup" /><span><small>Pickup</small><b>{ride.pickup.name}</b></span></li>
      <li><span className="dot drop" /><span><small>Drop</small><b>{ride.drop.name}</b></span></li>
    </ol>
  );
}

function Fare({ ride }) {
  const b = ride.breakdown;
  const pay = ride.payment;
  return (
    <dl className="ride-fare" data-testid="ride-fare">
      <div><dt>Base fare</dt><dd>{fmtINR(b.base)}</dd></div>
      <div><dt>Distance ({ride.distance_km} km)</dt><dd>{fmtINR(b.distance)}</dd></div>
      <div><dt>Time</dt><dd>{fmtINR(b.time)}</dd></div>
      {b.minimum_applied && <div><dt>Minimum fare adjustment</dt><dd>included</dd></div>}
      {b.surge_amount > 0 && <div><dt>Busy-hour charge ({b.surge_multiplier}x)</dt><dd>{fmtINR(b.surge_amount)}</dd></div>}
      <div><dt>GST (5%)</dt><dd>{fmtINR(b.gst)}</dd></div>
      {pay.tip > 0 && <div><dt>Tip for captain</dt><dd>{fmtINR(pay.tip)}</dd></div>}
      <div className="total"><dt>Total</dt><dd>{fmtINR(pay.amount_due)}</dd></div>
    </dl>
  );
}

function CancelSheet({ ride, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const fee = ride.state.cancel_fee;
  const go = async () => {
    setBusy(true);
    try {
      const out = await rideApi.cancel(ride.ride_id, reason);
      toast(out.fee_note || "Ride cancelled");
      onDone(out.ride);
    } catch (e) {
      toast.error(errorText(e, "Could not cancel the ride."));
      setBusy(false);
      onClose(true);
    }
  };
  return (
    <div className="sheet-back" role="presentation" onClick={() => !busy && onClose()}>
      <div className="sheet" role="dialog" aria-modal="true" aria-label="Cancel ride" onClick={(e) => e.stopPropagation()} data-testid="cancel-sheet">
        <h2>Why do you want to cancel?</h2>
        {fee > 0 ? (
          <p className="sheet-warn" data-testid="cancel-fee">Your captain is already on the way. A real ride would charge a ₹{fee} cancellation fee. In this demo nothing is charged.</p>
        ) : (
          <p className="sheet-ok" data-testid="cancel-free">Cancelling now is free.</p>
        )}
        <ul className="reason-list" role="radiogroup" aria-label="Reason">
          {ride.cancel_reasons.map((r) => (
            <li key={r}>
              <button type="button" role="radio" aria-checked={reason === r} className={reason === r ? "reason on" : "reason"} onClick={() => setReason(r)} data-testid="cancel-reason">{r}</button>
            </li>
          ))}
        </ul>
        <div className="sheet-actions">
          <button type="button" className="btn-ghost" onClick={() => onClose()} disabled={busy} data-testid="cancel-keep">Keep my ride</button>
          <button type="button" className="btn-danger" onClick={go} disabled={busy || !reason} data-testid="cancel-confirm">{busy ? "Cancelling..." : "Cancel ride"}</button>
        </div>
      </div>
    </div>
  );
}

function PaySection({ ride, onChange }) {
  const [tip, setTip] = useState(ride.payment.tip || 0);
  const [busy, setBusy] = useState(false);
  const pay = ride.payment;

  const payOnline = async () => {
    setBusy(true);
    try {
      const r = await rideApi.pay(ride.ride_id, "online", tip);
      if (r.mode === "paid") { onChange(r.ride); return; }
      if (r.mode === "razorpay") {
        if (!(await loadRazorpay())) throw new Error("Payment window could not load.");
        await new Promise((resolve, reject) => {
          const rz = new window.Razorpay({
            key: r.key_id, order_id: r.order_id, amount: r.amount_rupees * 100, currency: "INR", name: "DestinoWay", description: `Ride ${ride.ride_id}`,
            theme: { color: "#E8820C" },
            handler: async (resp) => {
              try { onChange(await rideApi.payVerify(ride.ride_id, resp)); toast.success("Payment received."); resolve(); } catch (e) { reject(e); }
            },
            modal: { ondismiss: () => resolve() },
          });
          rz.open();
        });
      } else {
        onChange(await rideApi.payConfirm(ride.ride_id));
        toast.success("Demo payment done. Nothing was charged.");
      }
    } catch (e) {
      toast.error(errorText(e, "Payment failed. Please try again."));
    } finally {
      setBusy(false);
    }
  };

  const cash = async () => {
    setBusy(true);
    try { const r = await rideApi.pay(ride.ride_id, "cash", 0); onChange(r.ride); } catch (e) { toast.error(errorText(e)); } finally { setBusy(false); }
  };

  if (pay.status === "paid") {
    return <div className="ride-paid" data-testid="ride-paid"><Check size={16} /> Paid {fmtINR(pay.amount_due)} {pay.method === "cash" ? "in cash" : "online"}{pay.tip > 0 ? ` (tip ${fmtINR(pay.tip)})` : ""}</div>;
  }
  return (
    <div className="ride-pay" data-testid="ride-pay">
      <h3>Pay for your ride</h3>
      <small>Add a tip for your captain (optional)</small>
      <div className="tip-row" role="radiogroup" aria-label="Tip">
        {TIPS.map((t) => (
          <button key={t} type="button" role="radio" aria-checked={tip === t} className={tip === t ? "tip on" : "tip"} onClick={() => setTip(t)} data-testid={`tip-${t}`}>{t === 0 ? "No tip" : `₹${t}`}</button>
        ))}
      </div>
      <button type="button" className="btn-primary" onClick={payOnline} disabled={busy} data-testid="ride-pay-online">
        {busy ? <Loader2 className="spin" size={16} /> : <CreditCard size={16} />} Pay {fmtINR(ride.fare + tip)} online
      </button>
      <button type="button" className="btn-ghost" onClick={cash} disabled={busy} data-testid="ride-pay-cash"><Banknote size={16} /> I will pay cash instead</button>
    </div>
  );
}

function Rate({ ride, onChange }) {
  const [stars, setStars] = useState(0);
  const [tags, setTags] = useState([]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  if (ride.rating) {
    return <div className="ride-rated" data-testid="ride-rated">You rated this ride {ride.rating.stars} / 5. Thank you!</div>;
  }
  const list = stars && stars <= 3 ? BAD_TAGS : GOOD_TAGS;
  const toggle = (t) => setTags((old) => (old.includes(t) ? old.filter((x) => x !== t) : [...old, t]));
  const send = async () => {
    setBusy(true);
    try { onChange(await rideApi.rate(ride.ride_id, { stars, tags, comment })); toast.success("Thanks for your feedback."); } catch (e) { toast.error(errorText(e)); setBusy(false); }
  };
  return (
    <div className="ride-rate" data-testid="ride-rate">
      <h3>How was your ride?</h3>
      <div className="stars" role="radiogroup" aria-label="Rating">
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" role="radio" aria-checked={stars === n} aria-label={`${n} star${n > 1 ? "s" : ""}`} className={n <= stars ? "star on" : "star"} onClick={() => { setStars(n); setTags([]); }} data-testid={`star-${n}`}><Star size={28} /></button>
        ))}
      </div>
      {stars > 0 && (
        <>
          <div className="tag-row">
            {list.map((t) => <button key={t} type="button" className={tags.includes(t) ? "tag on" : "tag"} aria-pressed={tags.includes(t)} onClick={() => toggle(t)}>{t}</button>)}
          </div>
          <textarea value={comment} maxLength={300} onChange={(e) => setComment(e.target.value)} placeholder="Anything else? (optional)" aria-label="Comment" rows={2} />
          <button type="button" className="btn-primary" onClick={send} disabled={busy} data-testid="rate-send">Submit</button>
        </>
      )}
    </div>
  );
}

export default function RideTrack() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user, loading: authLoading } = useAuth();
  const [ride, setRide] = useState(null);
  const [error, setError] = useState("");
  const [offline, setOffline] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const stageRef = useRef("");

  const apply = useCallback((r) => { setRide(r); setError(""); setOffline(false); }, []);

  // poll while the ride is going on: every 2 seconds on screen, every 10 seconds when the tab is hidden
  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate(`/login?redirect=${encodeURIComponent(`/ride/${id}`)}`, { replace: true }); return; }
    let live = true;
    let timer = null;
    const tick = async () => {
      try {
        const r = await rideApi.get(id);
        if (!live) return;
        apply(r);
        if (r.state.final) return;
      } catch (e) {
        if (!live) return;
        const status = e && e.response && e.response.status;
        if (status === 404 || status === 401) { setError(status === 404 ? "We could not find this ride." : "Please log in to see this ride."); return; }
        setOffline(true);
      }
      timer = setTimeout(tick, document.hidden ? 10000 : 2000);
    };
    tick();
    return () => { live = false; clearTimeout(timer); };
  }, [id, user, authLoading, navigate, apply]);

  // tell the rider when the stage changes, and keep the tab title useful
  useEffect(() => {
    if (!ride) return undefined;
    const stage = ride.state.stage;
    const title = `${STAGE_TITLE[stage] || "Ride"} | DestinoWay`;
    document.title = title;
    if (stageRef.current && stageRef.current !== stage) {
      const say = { arriving: "Captain found! They are on the way.", arrived: "Your captain has arrived.", in_progress: "Ride started. Have a safe trip!", completed: "You have reached your drop." };
      if (say[stage]) toast(say[stage]);
      if (navigator.vibrate && say[stage]) navigator.vibrate(120);
    }
    stageRef.current = stage;
    return () => { document.title = "DestinoWay"; };
  }, [ride]);

  const switchPay = async () => {
    try {
      const next = ride.payment.method === "cash" ? "online" : "cash";
      const out = await rideApi.pay(ride.ride_id, next, ride.payment.tip || 0, false);
      apply(out.ride);
    } catch (e) {
      toast.error(errorText(e));
    }
  };

  const share = async () => {
    try {
      const token = await rideApi.share(ride.ride_id);
      const url = `${window.location.origin}/ride/share/${token}`;
      if (navigator.share) { try { await navigator.share({ title: "Follow my ride", url }); return; } catch { /* fall through to copy */ } }
      await navigator.clipboard.writeText(url);
      toast.success("Link copied. Anyone with it can follow this ride.");
    } catch (e) {
      toast.error(errorText(e, "Could not create the link."));
    }
  };

  if (error) {
    return (
      <div className="empty-state" data-testid="ride-error"><h2>{error}</h2><Link className="btn-primary" to="/rides">Book a ride</Link></div>
    );
  }
  if (!ride) {
    return <div className="ride-loading" role="status"><Loader2 className="spin" size={22} /> Loading your ride...</div>;
  }

  const st = ride.state;
  const stage = st.stage;
  const live = isActiveStage(stage);
  const rebook = rideUrl({ pickup: ride.pickup, drop: ride.drop, vehicle: ride.vehicle.key });
  const followVehicle = stage === "arriving" || stage === "in_progress";

  return (
    <div className="ride-track" data-testid="ride-track" data-stage={stage}>
      <section className="ride-track-map">
        <Suspense fallback={<div className="ride-map ride-map-loading"><Loader2 className="spin" size={20} /></div>}>
          <RideMap pickup={ride.pickup} drop={ride.drop} route={ride.route} vehicle={live ? st.vehicle_pos : null} vehicleKind={ride.vehicle.key} follow={followVehicle} label="Live ride map" />
        </Suspense>
        {offline && <div className="ride-offline" role="status">Reconnecting...</div>}
      </section>

      <section className="ride-sheet" aria-live="polite">
        <div className="ride-head">
          <VehicleIcon kind={ride.vehicle.key} size={26} />
          <div>
            <h1 data-testid="ride-title">{STAGE_TITLE[stage]}</h1>
            <p data-testid="ride-headline">{stage === "scheduled" ? `Pickup ${whenText(ride.scheduled_for)}` : st.headline}</p>
          </div>
          {st.eta_min != null && live && stage !== "scheduled" && <span className="ride-eta" data-testid="ride-eta"><b>{st.eta_min}</b> min</span>}
        </div>

        {stage === "searching" && (
          <div className="ride-searching" data-testid="ride-searching"><Pulse /><span>Looking for the nearest {ride.vehicle.name.toLowerCase()} captain...</span></div>
        )}
        {(stage === "arriving" || stage === "arrived") && st.otp && <Otp code={st.otp} />}
        {st.captain && <Captain ride={ride} />}
        {stage === "in_progress" && (
          <div className="ride-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(st.progress * 100)} data-testid="ride-progress">
            <i style={{ width: `${Math.round(st.progress * 100)}%` }} />
          </div>
        )}

        <Route ride={ride} />

        {stage === "cancelled" && (
          <div className="ride-cancelled" data-testid="ride-cancelled">
            <p>Reason: {ride.cancelled.reason}</p>
            {ride.cancelled.fee > 0 && <p>A real ride would charge a ₹{ride.cancelled.fee} cancellation fee. Nothing was charged in this demo.</p>}
            {ride.cancelled.refund_demo > 0 && <p>Demo refund: {fmtINR(ride.cancelled.refund_demo)} would go back to your payment method.</p>}
          </div>
        )}

        {stage === "completed" && (
          <>
            <Fare ride={ride} />
            <PaySection ride={ride} onChange={apply} />
            {ride.payment.status === "paid" && <Rate ride={ride} onChange={apply} />}
          </>
        )}
        {live && (
          <>
            <div className="ride-fare-line"><span>{ride.vehicle.name} · {ride.distance_km} km</span><b>{fmtINR(ride.fare)}</b></div>
            <div className="ride-pay-line" data-testid="ride-pay-line">
              {ride.payment.method === "cash" ? <Banknote size={14} /> : <CreditCard size={14} />}
              <span>{ride.payment.method === "cash" ? "Pay cash to your captain" : "Pay online after the ride"}</span>
              <button type="button" className="link" onClick={switchPay} data-testid="ride-pay-change">Change</button>
            </div>
          </>
        )}

        <div className="ride-actions">
          {live && (
            <>
              <button type="button" className="btn-ghost" onClick={share} data-testid="ride-share"><Share2 size={15} /> Share ride</button>
              <button type="button" className="btn-ghost" disabled title="Demo ride: there is no real captain to call" data-testid="ride-call"><Phone size={15} /> Call</button>
              <button type="button" className="btn-ghost" disabled title="Demo ride: there is no real captain to message"><MessageCircle size={15} /> Chat</button>
            </>
          )}
          {st.can_cancel && <button type="button" className="btn-danger-ghost" onClick={() => setCancelOpen(true)} data-testid="ride-cancel"><X size={15} /> Cancel ride</button>}
          {(stage === "completed" || stage === "cancelled") && (
            <>
              {stage === "completed" && <Link className="btn-ghost" to={`/ride/${ride.ride_id}/receipt`} data-testid="ride-receipt"><FileText size={15} /> Receipt</Link>}
              <Link className="btn-primary" to={rebook} data-testid="ride-again"><RotateCcw size={15} /> Book again</Link>
              <Link className="btn-ghost" to="/dashboard?tab=rides">My rides <ChevronRight size={14} /></Link>
            </>
          )}
        </div>
        <p className="ride-demo" data-testid="ride-demo-note"><ShieldCheck size={13} /> {ride.demo_note}</p>
      </section>

      {cancelOpen && <CancelSheet ride={ride} onClose={(refresh) => { setCancelOpen(false); if (refresh) rideApi.get(id).then(apply).catch(() => {}); }} onDone={(r) => { setCancelOpen(false); apply(r); }} />}
    </div>
  );
}
