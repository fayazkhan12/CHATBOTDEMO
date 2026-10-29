import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plane, Hotel, BusFront, Car } from "lucide-react";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";
import { money, tripLine } from "../lib/format";

const icons = { flights: Plane, hotels: Hotel, buses: BusFront, cabs: Car, flight: Plane, hotel: Hotel, bus: BusFront, cab: Car };

const PAID = ["confirmed", "confirmed_demo", "paid"];
const STATUS_TEXT = {
  confirmed: "Confirmed",
  confirmed_demo: "Confirmed (demo)",
  paid: "Paid",
  pending_payment: "Payment pending",
  payment_failed: "Payment failed",
};

// An unpaid booking is created as soon as someone taps Reserve. Older versions of the site
// made a second one on the payment page, so only the newest unpaid one is shown, and none
// at all once the same offer has been paid for. `list` is newest first.
function visibleBookings(list) {
  const idOf = (b) => (b && b.item && b.item.id) || "";
  const paidFor = new Set(list.filter((b) => PAID.includes(b.status)).map(idOf).filter(Boolean));
  const seen = new Set();
  return list.filter((b) => {
    if (b.status !== "pending_payment") return true;
    const id = idOf(b);
    if (!id) return true;
    if (paidFor.has(id) || seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}

const bookedOn = (iso) => {
  const d = new Date(iso || "");
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
};

export default function Dashboard() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("bookings");
  const [bookings, setBookings] = useState([]);
  const [bookingsState, setBookingsState] = useState("loading"); // loading | ready | failed
  const [trips, setTrips] = useState([]);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate(`/login?redirect=${encodeURIComponent("/dashboard")}`); return; }
    http.get("/me/bookings")
      .then(({ data }) => { setBookings(data.bookings || []); setBookingsState("ready"); })
      .catch(() => setBookingsState("failed"));
    http.get("/me/trips").then(({ data }) => setTrips(data.trips || [])).catch(() => {});
  }, [user, loading, navigate]);

  if (loading || !user) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading your trips&hellip;</div>;

  const shown = visibleBookings(bookings);

  return (
    <div className="dash-page" data-testid="dashboard-page">
      <div className="dash-head">
        <div>
          <h1>Hey {user.name?.split(" ")[0] || "traveller"}</h1>
          <p>Everything about your journeys in one place.</p>
        </div>
      </div>
      <div className="dash-tabs">
        <button className={tab === "bookings" ? "active" : ""} onClick={() => setTab("bookings")} data-testid="tab-bookings">Bookings ({shown.length})</button>
        <button className={tab === "trips" ? "active" : ""} onClick={() => setTab("trips")} data-testid="tab-trips">Saved trips ({trips.length})</button>
        <button className={tab === "profile" ? "active" : ""} onClick={() => setTab("profile")} data-testid="tab-profile">Profile</button>
      </div>

      {tab === "bookings" && (
        bookingsState === "loading" ? (
          <div className="empty-state" data-testid="bookings-loading"><span className="spinner"/> Loading your bookings&hellip;</div>
        ) : bookingsState === "failed" ? (
          <div className="empty-state" data-testid="bookings-failed">Could not load your bookings right now. Please refresh the page.</div>
        ) : shown.length === 0 ? (
          <div className="empty-state">No bookings yet. <br/><button className="btn-primary" style={{marginTop:14}} onClick={() => navigate("/")}>Plan your first trip</button></div>
        ) : (
          shown.map(b => {
            const Icon = icons[b.service] || Plane;
            const line = tripLine(b.item);
            const on = bookedOn(b.created_at);
            const open = b.status === "pending_payment" || b.status === "payment_failed";
            return (
              <div key={b.booking_id} className="booking-card" data-testid={`booking-${b.booking_id}`}>
                <div style={{display:'flex',gap:16,alignItems:'center'}}>
                  <div style={{width:48,height:48,background:'rgba(232,130,12,0.1)',color:'var(--teal)',borderRadius:12,display:'grid',placeItems:'center',flexShrink:0}}><Icon size={22}/></div>
                  <div>
                    <strong>{b.item?.title}</strong>
                    <div style={{color:'var(--muted)',fontSize:13}}>{b.item?.brand}</div>
                    {line ? <div style={{color:'var(--muted)',fontSize:13}} data-testid="booking-line">{line}</div> : null}
                    <small>Booking &middot; {b.booking_id} &middot; {money(b.amount_rupees)}{on ? ` · ${on}` : ""}</small>
                  </div>
                </div>
                <div className="booking-actions">
                  <span className={`booking-status ${b.status}`}>{STATUS_TEXT[b.status] || (b.status || "").replace(/_/g, " ")}</span>
                  {open
                    ? <button className="btn-primary" onClick={() => navigate(`/checkout/${b.booking_id}`)} data-testid={`continue-${b.booking_id}`}>Continue</button>
                    : <button className="btn-ghost" onClick={() => navigate(`/booking/${b.booking_id}`)} data-testid={`voucher-${b.booking_id}`}>View</button>}
                </div>
              </div>
            );
          })
        )
      )}

      {tab === "trips" && (
        trips.length === 0 ? (
          <div className="empty-state">No saved trips yet.</div>
        ) : (
          trips.map(t => (
            <div key={t.share_id} className="booking-card" data-testid={`trip-${t.share_id}`}>
              <div>
                <strong>{t.title}</strong>
                <div style={{color:'var(--muted)',fontSize:13}}>{t.origin} &rarr; {t.destination} &middot; {t.dates}</div>
                <small>{t.items?.length || 0} items</small>
              </div>
              <button className="btn-ghost" onClick={() => navigate(`/trip/${t.share_id}`)}>Open</button>
            </div>
          ))
        )
      )}

      {tab === "profile" && (
        <div style={{maxWidth:500,background:'var(--surface)',border:'1px solid var(--line)',borderRadius:14,padding:28}} data-testid="profile-card">
          <div style={{display:'flex',alignItems:'center',gap:16,marginBottom:20}}>
            {user.picture ? <img src={user.picture} alt="" style={{width:60,height:60,borderRadius:'50%'}}/> : <div style={{width:60,height:60,borderRadius:'50%',background:'var(--surface-2)',display:'grid',placeItems:'center',color:'var(--teal)',fontSize:24,fontFamily:'Jost, sans-serif'}}>{user.name?.[0]}</div>}
            <div>
              <div style={{fontFamily:'Jost, sans-serif',fontSize:22}}>{user.name}</div>
              <div style={{color:'var(--muted)',fontSize:13}}>{user.email}</div>
            </div>
          </div>
          <div style={{color:'var(--muted)',fontSize:13,lineHeight:1.6}}>Signed in via {user.provider || "email"}. Your bookings and saved trips are tied to this account.</div>
        </div>
      )}
    </div>
  );
}
