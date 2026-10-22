import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { http } from "../lib/api";

export default function TripShare() {
  const { shareId } = useParams();
  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    http.get(`/trips/${shareId}`).then(({ data }) => setTrip(data)).catch(() => {}).finally(() => setLoading(false));
  }, [shareId]);

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading trip…</div>;
  if (!trip) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Trip not found.</div>;

  return (
    <div style={{maxWidth:900,margin:'40px auto',padding:'0 24px'}} data-testid="trip-share-page">
      <h1 style={{fontFamily:'Playfair Display',fontSize:40}}>{trip.title}</h1>
      <p style={{color:'var(--muted)'}}>{trip.origin} → {trip.destination} · {trip.dates}</p>
      <div style={{display:'grid',gap:14,marginTop:30}}>
        {(trip.items || []).map((it, i) => (
          <div key={i} className="booking-card">
            <div>
              <strong>{it.title}</strong>
              <div style={{color:'var(--muted)',fontSize:13}}>{it.brand}</div>
            </div>
            <div style={{fontFamily:'Playfair Display',fontSize:22}}>₹{Number(it.price||0).toLocaleString("en-IN")}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
