import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCircle2, Clock3, Download, Copy } from "lucide-react";
import { toast } from "sonner";
import { http } from "../lib/api";
import { money, tripLine } from "../lib/format";

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
const LABEL = { color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.1em" };

export default function BookingConfirm() {
  const { bookingId } = useParams();
  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    http.get(`/bookings/${bookingId}`).then(({ data }) => setBooking(data)).catch(() => {}).finally(() => setLoading(false));
  }, [bookingId]);

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading voucher&hellip;</div>;
  if (!booking) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Booking not found.</div>;

  const confirmed = booking.status === "confirmed" || booking.status === "paid" || booking.status === "confirmed_demo";
  const item = booking.item || {};
  const isDemo = booking.status === "confirmed_demo" || item.mode === "DEMO";
  const roomName = item.room_name || "";
  const heading = roomName && item.title && item.title.endsWith(` - ${roomName}`)
    ? item.title.slice(0, -(roomName.length + 3))
    : item.title;
  const when = tripLine(item);
  const isHotel = (item.type || booking.service) === "hotel";

  const copyId = async () => {
    try {
      await navigator.clipboard.writeText(booking.booking_id);
      toast.success("Booking ID copied");
    } catch {
      toast.error("Could not copy. Please select the ID and copy it.");
    }
  };

  return (
    <div className="voucher-page" style={{maxWidth:720,margin:'40px auto 80px',padding:'0 24px'}} data-testid="confirm-page">
      <div style={{background:'var(--surface)',border:'1px solid var(--line-strong)',borderRadius:20,padding:40,textAlign:'center'}}>
        <div style={{width:72,height:72,margin:'0 auto 20px',borderRadius:'50%',background:confirmed?'rgba(232,130,12,0.15)':'rgba(245,158,11,0.15)',display:'grid',placeItems:'center',color:confirmed?'var(--teal)':'var(--gold)'}}>
          {confirmed ? <CheckCircle2 size={36}/> : <Clock3 size={36}/>}
        </div>
        <h1 style={{fontFamily:'Jost, sans-serif',fontSize:36,margin:'0 0 8px'}} data-testid="confirm-heading">{confirmed ? "Booking confirmed!" : "Payment pending"}</h1>
        <p style={{color:'var(--muted)',marginBottom:28}}>Reference <code style={{color:'var(--teal)',fontFamily:MONO}}>{booking.booking_id}</code>{isDemo && <span className="badge-demo" style={{marginLeft:8}} data-testid="confirm-demo-badge">DEMO</span>}</p>

        {isDemo && (
          <div className="dl-note dl-demo" style={{textAlign:'left',marginBottom:24}} role="note" data-testid="confirm-demo-note">
            This is a demo booking. No real ticket or hotel reservation was made and no real money was charged.
          </div>
        )}

        {item.image && <img src={item.image} alt="" style={{width:'100%',maxHeight:220,objectFit:'cover',borderRadius:14,marginBottom:24}} onError={(e) => { e.currentTarget.style.display = 'none'; }}/>}

        {heading ? (
          <div style={{textAlign:'left',marginBottom:24}}>
            <div style={{fontFamily:'Jost, sans-serif',fontSize:22}} data-testid="confirm-title">{heading}</div>
            {item.brand ? <div style={{color:'var(--muted)',fontSize:13}}>{item.brand}</div> : null}
          </div>
        ) : null}

        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,textAlign:'left',marginBottom:28}} className="voucher-grid">
          <div><div style={LABEL}>Service</div><strong style={{textTransform:'capitalize'}}>{booking.service}</strong></div>
          <div><div style={LABEL}>{confirmed && !isDemo ? "Total paid" : "Total"}</div><strong>{money(booking.amount_rupees)}</strong></div>
          {roomName ? <div><div style={LABEL}>Room</div><strong>{roomName}</strong></div> : null}
          {when ? <div><div style={LABEL}>{isHotel ? "Stay" : "Trip"}</div><strong data-testid="confirm-when">{when}</strong></div> : null}
          {item.cancellation ? <div><div style={LABEL}>Cancellation</div><strong>{item.cancellation}</strong></div> : null}
          <div><div style={LABEL}>Traveller</div><strong>{booking.traveller?.name}</strong></div>
          <div><div style={LABEL}>Contact</div><strong style={{wordBreak:'break-word'}}>{booking.traveller?.email}</strong></div>
        </div>

        <div className="no-print" style={{display:'flex',gap:12,justifyContent:'center',flexWrap:'wrap'}}>
          {!confirmed && <button className="btn-primary" onClick={() => navigate(`/checkout/${booking.booking_id}`)} data-testid="complete-payment-btn">Complete payment</button>}
          <button className={confirmed ? "btn-primary" : "btn-ghost"} onClick={() => window.print()} data-testid="print-btn"><Download size={14}/> Print voucher</button>
          <button className="btn-ghost" onClick={copyId} data-testid="share-btn"><Copy size={14}/> Copy booking ID</button>
          <button className="btn-ghost" onClick={() => navigate("/dashboard")} data-testid="dashboard-btn">My bookings</button>
        </div>
      </div>
    </div>
  );
}
