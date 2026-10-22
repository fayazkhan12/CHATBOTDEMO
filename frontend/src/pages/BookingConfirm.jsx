import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { CheckCircle2, Download, Share2 } from "lucide-react";
import { toast } from "sonner";
import { http } from "../lib/api";

export default function BookingConfirm() {
  const { bookingId } = useParams();
  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    http.get(`/bookings/${bookingId}`).then(({ data }) => setBooking(data)).catch(() => {}).finally(() => setLoading(false));
  }, [bookingId]);

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading voucher…</div>;
  if (!booking) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Booking not found.</div>;

  const confirmed = booking.status === "confirmed" || booking.status === "paid" || booking.status === "confirmed_demo";

  return (
    <div style={{maxWidth:720,margin:'40px auto 80px',padding:'0 24px'}} data-testid="confirm-page">
      <div style={{background:'var(--surface)',border:'1px solid var(--line-strong)',borderRadius:20,padding:40,textAlign:'center'}}>
        <div style={{width:72,height:72,margin:'0 auto 20px',borderRadius:'50%',background:'rgba(45,212,191,0.15)',display:'grid',placeItems:'center',color:'var(--teal)'}}>
          <CheckCircle2 size={36}/>
        </div>
        <h1 style={{fontFamily:'Playfair Display',fontSize:36,margin:'0 0 8px'}}>{confirmed ? "Booking confirmed!" : "Booking pending"}</h1>
        <p style={{color:'var(--muted)',marginBottom:28}}>Reference <code style={{color:'var(--teal)',fontFamily:'DM Mono'}}>{booking.booking_id}</code> · {booking.status === "confirmed_demo" && <span className="badge-demo" style={{marginLeft:6}}>DEMO</span>}</p>

        {booking.item?.image && <img src={booking.item.image} alt="" style={{width:'100%',maxHeight:220,objectFit:'cover',borderRadius:14,marginBottom:24}}/>}

        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,textAlign:'left',marginBottom:28}}>
          <div><div style={{color:'var(--muted)',fontSize:11,textTransform:'uppercase',letterSpacing:'0.1em'}}>Service</div><strong style={{textTransform:'capitalize'}}>{booking.service}</strong></div>
          <div><div style={{color:'var(--muted)',fontSize:11,textTransform:'uppercase',letterSpacing:'0.1em'}}>Total paid</div><strong>₹{Number(booking.amount_rupees).toLocaleString("en-IN")}</strong></div>
          <div><div style={{color:'var(--muted)',fontSize:11,textTransform:'uppercase',letterSpacing:'0.1em'}}>Traveller</div><strong>{booking.traveller?.name}</strong></div>
          <div><div style={{color:'var(--muted)',fontSize:11,textTransform:'uppercase',letterSpacing:'0.1em'}}>Contact</div><strong>{booking.traveller?.email}</strong></div>
        </div>

        <div style={{display:'flex',gap:12,justifyContent:'center',flexWrap:'wrap'}}>
          <button className="btn-primary" onClick={() => window.print()} data-testid="print-btn"><Download size={14} style={{marginRight:6}}/> Print voucher</button>
          <button className="btn-ghost" onClick={() => { navigator.clipboard?.writeText(window.location.href); toast.success("Link copied"); }} data-testid="share-btn"><Share2 size={14} style={{marginRight:6}}/> Share</button>
          <button className="btn-ghost" onClick={() => navigate("/dashboard")} data-testid="dashboard-btn">My bookings</button>
        </div>
      </div>
    </div>
  );
}
