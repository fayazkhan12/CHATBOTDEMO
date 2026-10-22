import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plane, Hotel, BusFront, Car } from "lucide-react";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";

const icons = { flights: Plane, hotels: Hotel, buses: BusFront, cabs: Car, flight: Plane, hotel: Hotel, bus: BusFront, cab: Car };

export default function Dashboard() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();
  const [tab, setTab] = useState("bookings");
  const [bookings, setBookings] = useState([]);
  const [trips, setTrips] = useState([]);

  useEffect(() => {
    if (loading) return;
    if (!user) { navigate("/login"); return; }
    http.get("/me/bookings").then(({ data }) => setBookings(data.bookings || [])).catch(() => {});
    http.get("/me/trips").then(({ data }) => setTrips(data.trips || [])).catch(() => {});
  }, [user, loading, navigate]);

  if (loading || !user) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading your trips…</div>;

  return (
    <div className="dash-page" data-testid="dashboard-page">
      <div className="dash-head">
        <div>
          <h1>Hey {user.name?.split(" ")[0] || "traveller"}</h1>
          <p>Everything about your journeys in one place.</p>
        </div>
      </div>
      <div className="dash-tabs">
        <button className={tab === "bookings" ? "active" : ""} onClick={() => setTab("bookings")} data-testid="tab-bookings">Bookings ({bookings.length})</button>
        <button className={tab === "trips" ? "active" : ""} onClick={() => setTab("trips")} data-testid="tab-trips">Saved trips ({trips.length})</button>
        <button className={tab === "profile" ? "active" : ""} onClick={() => setTab("profile")} data-testid="tab-profile">Profile</button>
      </div>

      {tab === "bookings" && (
        bookings.length === 0 ? (
          <div className="empty-state">No bookings yet. <br/><button className="btn-primary" style={{marginTop:14}} onClick={() => navigate("/")}>Plan your first trip</button></div>
        ) : (
          bookings.map(b => {
            const Icon = icons[b.service] || Plane;
            return (
              <div key={b.booking_id} className="booking-card" data-testid={`booking-${b.booking_id}`}>
                <div style={{display:'flex',gap:16,alignItems:'center'}}>
                  <div style={{width:48,height:48,background:'rgba(45,212,191,0.1)',color:'var(--teal)',borderRadius:12,display:'grid',placeItems:'center'}}><Icon size={22}/></div>
                  <div>
                    <strong>{b.item?.title}</strong>
                    <div style={{color:'var(--muted)',fontSize:13}}>{b.item?.brand}</div>
                    <small>Booking · {b.booking_id} · ₹{Number(b.amount_rupees).toLocaleString("en-IN")}</small>
                  </div>
                </div>
                <span className={`booking-status ${b.status}`}>{(b.status || "").replace("_", " ")}</span>
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
                <div style={{color:'var(--muted)',fontSize:13}}>{t.origin} → {t.destination} · {t.dates}</div>
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
            {user.picture ? <img src={user.picture} alt="" style={{width:60,height:60,borderRadius:'50%'}}/> : <div style={{width:60,height:60,borderRadius:'50%',background:'var(--surface-2)',display:'grid',placeItems:'center',color:'var(--teal)',fontSize:24,fontFamily:'Playfair Display'}}>{user.name?.[0]}</div>}
            <div>
              <div style={{fontFamily:'Playfair Display',fontSize:22}}>{user.name}</div>
              <div style={{color:'var(--muted)',fontSize:13}}>{user.email}</div>
            </div>
          </div>
          <div style={{color:'var(--muted)',fontSize:13,lineHeight:1.6}}>Signed in via {user.provider || "email"}. Your bookings and saved trips are tied to this account.</div>
        </div>
      )}
    </div>
  );
}
