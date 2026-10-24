import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { http, loadRazorpay } from "../lib/api";
import { useVoiceDock, useFormGuide, CHECKOUT_VOICE_FIELDS, highlightPay } from "../lib/useVoiceDock";
import { useAuth } from "../lib/auth";
import { ShieldCheck } from "lucide-react";
import { validateTraveller } from "../lib/validate";

export default function Checkout() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [form, setForm] = useState({ name: user?.name || "", email: user?.email || "", phone: "", address: "", city: "", state: "" });
  const [errors, setErrors] = useState({});
  // re-check the fields that are showing an error while the user fixes them
  useEffect(() => {
    setErrors((old) => {
      if (!Object.keys(old).length) return old;
      const now = validateTraveller(form);
      const next = {};
      Object.keys(old).forEach((k) => { if (now[k]) next[k] = now[k]; });
      return next;
    });
  }, [form]);
  const check = (k) => setErrors((old) => {
    const msg = validateTraveller(form)[k];
    const next = { ...old };
    if (msg) next[k] = msg; else delete next[k];
    return next;
  });
  const bad = (k) => (errors[k] ? <small className="field-error" role="alert">{errors[k]}</small> : null);

  useEffect(() => {
    http.get(`/bookings/${bookingId}`).then(({ data }) => {
      setBooking(data);
      setForm(f => ({ ...f, name: data.traveller?.name || user?.name || "", email: data.traveller?.email || user?.email || "" }));
    }).catch(() => toast.error("Booking not found")).finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bookingId]);

  const pay = async (e) => {
    e.preventDefault();
    const found = validateTraveller(form);
    setErrors(found);
    const firstBad = Object.keys(found)[0];
    if (firstBad) {
      toast.error(found[firstBad]);
      const el = document.querySelector(`[data-testid="checkout-${firstBad}"]`);
      if (el && el.focus) el.focus();
      return;
    }
    setPaying(true);
    try {
      // Fetch Razorpay order again to get fresh key_id (we already have one on booking)
      const { data: order } = await http.post("/bookings", {
        item: booking.item, traveller: form,
        amount_rupees: booking.amount_rupees, service: booking.service,
      });
      const bid = order.booking_id || bookingId;
      if (!order.razorpay_order_id) {
        // Razorpay not configured — demo path
        await http.post("/bookings/demo-confirm", { booking_id: bid });
        toast.success("Booking confirmed in DEMO mode.");
        navigate(`/booking/${bid}`);
        return;
      }
      const loaded = await loadRazorpay();
      if (!loaded) { toast.error("Could not load payment gateway."); setPaying(false); return; }
      const options = {
        key: order.razorpay_key_id,
        amount: order.amount_rupees * 100,
        currency: "INR",
        name: "DestinoWay",
        description: `Booking ${bid}`,
        order_id: order.razorpay_order_id,
        prefill: { name: form.name, email: form.email, contact: form.phone },
        theme: { color: "#2DD4BF" },
        handler: async (response) => {
          try {
            await http.post("/bookings/verify", {
              booking_id: bid,
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });
            toast.success("Payment confirmed!");
            navigate(`/booking/${bid}`);
          } catch {
            toast.error("Payment verification failed. Contact support.");
          }
        },
        modal: { ondismiss: () => setPaying(false) },
      };
      new window.Razorpay(options).open();
    } catch (err) {
      const detail = err && err.response && err.response.data && err.response.data.detail;
      const msg = typeof detail === "string" ? detail : "Could not start payment.";
      toast.error(msg);
      if (typeof detail === "string") {
        const key = /city/i.test(detail) ? "city" : /address/i.test(detail) ? "address" : /email/i.test(detail) ? "email" : /mobile|phone/i.test(detail) ? "phone" : /name/i.test(detail) ? "name" : null;
        if (key) {
          setErrors((o) => ({ ...o, [key]: msg }));
          const el = document.querySelector(`[data-testid="checkout-${key}"]`);
          if (el && el.focus) el.focus();
        }
      }
      setPaying(false);
    }
  };

  const voiceGuide = useFormGuide({
    fields: CHECKOUT_VOICE_FIELDS,
    onValue: (key, value) => setForm((f) => ({ ...f, [key]: value })),
    onDone: highlightPay,
  });
  useVoiceDock({
    maxTurns: 30,
    onStart: () => voiceGuide.start(),
    onText: (said) => voiceGuide.handle(said),
  });

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading…</div>;
  if (!booking) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Booking not found.</div>;

  return (
    <div className="checkout-page" data-testid="checkout-page">
      <form className="checkout-form" onSubmit={pay} noValidate>
        <h2>Traveller details</h2>
        <div className="form-row">
          <label><span>Full name</span><input value={form.name} onChange={(e)=>setForm({...form,name:e.target.value})} required onBlur={() => check("name")} aria-invalid={!!errors.name} data-testid="checkout-name"/>{bad("name")}</label>
          <label><span>Email</span><input type="email" value={form.email} onChange={(e)=>setForm({...form,email:e.target.value})} required onBlur={() => check("email")} aria-invalid={!!errors.email} data-testid="checkout-email"/>{bad("email")}</label>
        </div>
        <div className="form-row">
          <label><span>Mobile (with code)</span><input value={form.phone} onChange={(e)=>setForm({...form,phone:e.target.value})} placeholder="+91 9000090000" required onBlur={() => check("phone")} aria-invalid={!!errors.phone} data-testid="checkout-phone"/>{bad("phone")}</label>
          <label><span>City</span><input value={form.city} onChange={(e)=>setForm({...form,city:e.target.value})} onBlur={() => check("city")} aria-invalid={!!errors.city} data-testid="checkout-city"/>{bad("city")}</label>
        </div>
        <div className="form-row single">
          <label><span>Address</span><input value={form.address} onChange={(e)=>setForm({...form,address:e.target.value})} onBlur={() => check("address")} aria-invalid={!!errors.address} data-testid="checkout-address"/>{bad("address")}</label>
        </div>
        <button type="submit" className="btn-primary" style={{width:'100%',padding:'15px',marginTop:14,fontSize:15}} disabled={paying} data-testid="pay-btn">
          {paying ? "Processing…" : `Pay ₹${Number(booking.amount_rupees).toLocaleString("en-IN")} securely`}
        </button>
        <div style={{display:'flex',alignItems:'center',gap:8,color:'var(--muted)',fontSize:12,marginTop:14,justifyContent:'center'}}>
          <ShieldCheck size={14} style={{color:'var(--teal)'}}/> Razorpay secured · 256-bit encrypted
        </div>
      </form>

      <aside className="summary-sticky">
        <h3>Order summary</h3>
        <div style={{borderRadius:12,overflow:'hidden',marginBottom:16}}>
          {booking.item?.image && <img src={booking.item.image} alt="" style={{width:'100%',aspectRatio:'4/3',objectFit:'cover'}}/>}
        </div>
        <div style={{fontFamily:'Playfair Display,serif',fontSize:20}}>{booking.item?.title}</div>
        <div style={{color:'var(--muted)',fontSize:13,marginBottom:14}}>{booking.item?.brand}</div>
        <div className="booking-row"><span>Service</span><span style={{textTransform:'capitalize'}}>{booking.service}</span></div>
        <div className="booking-row"><span>Booking ID</span><span style={{fontFamily:'DM Mono'}}>{booking.booking_id}</span></div>
        <div className="booking-row"><span>Taxes & fees</span><span>Included</span></div>
        <div className="booking-row"><span>Total</span><span>₹{Number(booking.amount_rupees).toLocaleString("en-IN")}</span></div>
      </aside>
    </div>
  );
}
