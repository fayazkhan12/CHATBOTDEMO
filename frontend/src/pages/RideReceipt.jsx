import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Loader2, Printer } from "lucide-react";
import { useAuth } from "../lib/auth";
import { errorText, fmtINR, rideApi } from "../lib/rides";

const stamp = (iso) => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "numeric", minute: "2-digit", hour12: true });
};

export default function RideReceipt() {
  const { id } = useParams();
  const { user, loading } = useAuth();
  const [ride, setRide] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (loading || !user) return;
    rideApi.get(id).then(setRide).catch((e) => setError(errorText(e, "We could not find this ride.")));
  }, [id, user, loading]);

  if (!loading && !user) return <div className="empty-state"><h2>Please log in to see this receipt</h2><Link className="btn-primary" to={`/login?redirect=/ride/${id}/receipt`}>Log in</Link></div>;
  if (error) return <div className="empty-state" data-testid="receipt-error"><h2>{error}</h2><Link className="btn-primary" to="/dashboard?tab=rides">My rides</Link></div>;
  if (!ride) return <div className="ride-loading" role="status"><Loader2 className="spin" size={22} /> Loading receipt...</div>;

  const b = ride.breakdown;
  const p = ride.payment;
  const c = ride.state.captain;
  const done = ride.state.stage === "completed";
  return (
    <div className="receipt-page" data-testid="receipt-page">
      <article className="receipt">
        <header>
          <h1>Ride receipt</h1>
          <span className="demo-chip">Demo</span>
        </header>
        <p className="receipt-id">{ride.ride_id} · {stamp(ride.created_at)}</p>
        <ol className="ride-route-list">
          <li><span className="dot pickup" /><span><small>Pickup</small><b>{ride.pickup.name}</b></span></li>
          <li><span className="dot drop" /><span><small>Drop</small><b>{ride.drop.name}</b></span></li>
        </ol>
        <dl className="ride-fare">
          <div><dt>Ride</dt><dd>{ride.vehicle.name} · {ride.distance_km} km · {ride.duration_min} min</dd></div>
          {c && <div><dt>Captain</dt><dd>{c.name} · {c.plate}</dd></div>}
          <div><dt>Base fare</dt><dd>{fmtINR(b.base)}</dd></div>
          <div><dt>Distance</dt><dd>{fmtINR(b.distance)}</dd></div>
          <div><dt>Time</dt><dd>{fmtINR(b.time)}</dd></div>
          {b.surge_amount > 0 && <div><dt>Busy-hour charge ({b.surge_multiplier}x)</dt><dd>{fmtINR(b.surge_amount)}</dd></div>}
          <div><dt>GST (5%)</dt><dd>{fmtINR(b.gst)}</dd></div>
          {p.tip > 0 && <div><dt>Tip</dt><dd>{fmtINR(p.tip)}</dd></div>}
          <div className="total"><dt>Total</dt><dd>{fmtINR(p.amount_due)}</dd></div>
          <div><dt>Payment</dt><dd>{p.method === "cash" ? "Cash" : "Online"} · {p.status === "paid" ? "Paid" : done ? "Pending" : "On the ride"}</dd></div>
        </dl>
        <p className="receipt-note">{ride.demo_note} This is not a tax invoice.</p>
      </article>
      <div className="receipt-actions no-print">
        <button type="button" className="btn-primary" onClick={() => window.print()} data-testid="receipt-print"><Printer size={15} /> Print or save as PDF</button>
        <Link className="btn-ghost" to={`/ride/${ride.ride_id}`}>Back to ride</Link>
      </div>
    </div>
  );
}
