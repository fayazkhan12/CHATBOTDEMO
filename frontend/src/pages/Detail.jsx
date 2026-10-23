import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useVoiceDock, markVoiceFlow } from "../lib/useVoiceDock";
import { isReserveIntent, isBackIntent } from "../lib/voicecmd";
import { ArrowLeft, Check, Clock3, MapPin, Star, Users, CalendarDays } from "lucide-react";
import { toast } from "sonner";
import { http } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function Detail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [item, setItem] = useState(null);
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);

  useEffect(() => {
    http.get(`/travel/detail/${encodeURIComponent(id)}`)
      .then(({ data }) => setItem(data))
      .catch(() => toast.error("This option is no longer available. Please search again."))
      .finally(() => setLoading(false));
  }, [id]);

  const book = async () => {
    if (!user) {
      toast.info("Please log in to continue to checkout.");
      navigate(`/login?redirect=${encodeURIComponent(window.location.pathname)}`);
      return;
    }
    setBooking(true);
    try {
      const { data } = await http.post("/bookings", {
        item,
        traveller: { name: user.name, email: user.email, contact: user.contact || "" },
        amount_rupees: Math.round(item.price),
        service: item.type || "hotel",
      });
      navigate(`/checkout/${data.booking_id}`);
    } catch (e) {
      toast.error("Could not start checkout. Try again.");
    } finally {
      setBooking(false);
    }
  };

  useVoiceDock({
    maxTurns: 5,
    onStart: () => ({ say: 'Say "reserve now" to book this one, or "back" to see other options.', listen: true }),
    onText: (said) => {
      if (isBackIntent(said)) { navigate(-1); return { listen: false }; }
      if (isReserveIntent(said)) { markVoiceFlow(); book(); return { say: "Reserving this for you.", listen: false }; }
      return { say: 'Sorry. Say "reserve now" or "back".', listen: true };
    },
  });

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading details…</div>;

  if (!item) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Option not found. <button className="btn-primary" onClick={() => navigate(-1)} style={{marginTop:14}}>Go back</button></div>;

  const amenities = item.amenities || ["Breakfast included", "Free cancellation", "24×7 concierge", "Wi-Fi"];
  const nights = item.nights || 1;

  return (
    <div className="detail-page" data-testid="detail-page">
      <button className="btn-ghost" onClick={() => navigate(-1)} style={{marginBottom:20}} data-testid="back-btn"><ArrowLeft size={14}/> Back</button>
      <div className="detail-hero"><img src={item.image} alt={item.title}/></div>
      <div className="detail-grid">
        <div className="detail-body">
          <span className={item.mode === "LIVE" ? "badge-live" : "badge-demo"}>{item.mode}</span>
          <h1 data-testid="detail-title">{item.title}</h1>
          <div className="detail-brand">{item.brand}</div>
          <div style={{display:'flex',flexWrap:'wrap',gap:20,color:'var(--muted)',fontSize:14,marginBottom:20}}>
            {item.location && <span><MapPin size={14} style={{marginRight:4,verticalAlign:'-2px'}}/> {item.location}</span>}
            {item.rating && <span><Star size={14} style={{color:'var(--gold)',fill:'var(--gold)',marginRight:4,verticalAlign:'-2px'}}/> {item.rating} rating</span>}
            {item.duration && <span><Clock3 size={14} style={{marginRight:4,verticalAlign:'-2px'}}/> {item.duration}</span>}
          </div>
          <p style={{color:'var(--muted)',lineHeight:1.7}}>
                       {item.title}{item.brand ? ` — ${item.brand}` : ''}.
          </p>
          <div className="detail-section">
            <h3>What's included</h3>
            <div className="amen-grid">
              {amenities.map(a => <span key={a}><Check size={14} style={{color:'var(--teal)'}}/> {a}</span>)}
            </div>
          </div>
          <div className="detail-section">
            <h3>Cancellation policy</h3>
                       <p style={{color:'var(--muted)',fontSize:13,lineHeight:1.6}}>
              {(item.meta || []).includes('Free cancellation')
                ? 'The supplier lists free cancellation on this rate. Please check the exact terms before you pay.'
                : 'Cancellation terms depend on the rate you choose. Please check them before you pay.'}
            </p>
          </div>
        </div>

        <aside className="booking-sticky" data-testid="booking-card">
          <h4>Total price</h4>
          <div className="booking-price">₹{Number(item.price).toLocaleString("en-IN")}</div>
          <div style={{color:'var(--muted)',fontSize:12,marginBottom:16}}>Taxes & fees included · {item.currency}</div>
          <div className="booking-row"><span><CalendarDays size={13} style={{marginRight:6,verticalAlign:'-2px'}}/>Stay / Trip</span><span>{nights} {nights === 1 ? "night" : "nights"}</span></div>
          <div className="booking-row"><span><Users size={13} style={{marginRight:6,verticalAlign:'-2px'}}/>Travellers</span><span>2 guests</span></div>
          <div className="booking-row"><span>Service fee</span><span>Included</span></div>
          <div className="booking-row"><span>Total</span><span>₹{Number(item.price).toLocaleString("en-IN")}</span></div>
          <button
            className="btn-primary"
            style={{width:'100%',padding:'14px',marginTop:16,fontSize:15}}
            onClick={book}
            disabled={booking}
            data-testid="book-now-btn"
          >
            {booking ? "Preparing…" : "Reserve now"}
          </button>
          <p style={{color:'var(--muted)',fontSize:11,textAlign:'center',marginTop:10,lineHeight:1.5}}>
            You won't be charged until the next step. Razorpay-secured.
          </p>
        </aside>
      </div>
    </div>
  );
}
