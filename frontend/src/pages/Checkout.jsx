import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { http, loadRazorpay } from "../lib/api";
import { useVoiceDock, useFormGuide, CHECKOUT_VOICE_FIELDS, highlightPay } from "../lib/useVoiceDock";
import { useAuth } from "../lib/auth";
import { ShieldCheck } from "lucide-react";
import { validateTraveller, cleanName, tidyTraveller } from "../lib/validate";
import { money, tripLine } from "../lib/format";

const MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";

export default function Checkout() {
  const { bookingId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [booking, setBooking] = useState(null);
  const [loading, setLoading] = useState(true);
  const [paying, setPaying] = useState(false);
  const [form, setForm] = useState({ name: cleanName(user?.name), email: user?.email || "", phone: "", address: "", city: "", state: "" });
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
      setForm(f => ({ ...f, name: cleanName(data.traveller?.name) || cleanName(user?.name), email: data.traveller?.email || user?.email || "" }));
    }).catch((err) => {
      if (err && err.response && err.response.status === 401) {
        toast.info("Please log in to continue.");
        navigate(`/login?redirect=${encodeURIComponent(`/checkout/${bookingId}`)}`);
        return;
      }
      toast.error("Booking not found");
    }).finally(() => setLoading(false));
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
      // The server keeps the unpaid booking made on the details page and attaches these details to it.
      const { data: order } = await http.post("/bookings", {
        item: booking.item, traveller: tidyTraveller(form),
        amount_rupees: booking.amount_rupees, service: booking.service,
      });
      const bid = order.booking_id || bookingId;
      if (!order.razorpay_order_id) {
        // no payment gateway for this booking: demo path
        try {
          await http.post("/bookings/demo-confirm", { booking_id: bid });
        } catch (err) {
          if (err && err.response && err.response.status === 404) {
            toast.error("Online payment is not switched on yet, so this booking cannot be completed.");
            setPaying(false);
            return;
          }
          throw err;
        }
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
        theme: { color: "#E8820C" },
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
            setPaying(false);
          }
        },
        modal: { ondismiss: () => setPaying(false) },
      };
      const checkoutWindow = new window.Razorpay(options);
      if (typeof checkoutWindow.on === "function") {
        checkoutWindow.on("payment.failed", (res) => {
          const why = res && res.error && res.error.description;
          toast.error(typeof why === "string" && why ? why : "Payment failed. Please try again.");
          setPaying(false);
        });
      }
      checkoutWindow.open();
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

  if (loading) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}><span className="spinner"/> Loading&hellip;</div>;
  if (!booking) return <div className="empty-state" style={{maxWidth:600,margin:'80px auto'}}>Booking not found.</div>;

  const item = booking.item || {};
  const isDemoItem = item.mode === "DEMO";
  const hasGateway = !!booking.razorpay_order_id;
  const total = money(booking.amount_rupees);
  const roomName = item.room_name || "";
  const heading = roomName && item.title && item.title.endsWith(` - ${roomName}`)
    ? item.title.slice(0, -(roomName.length + 3))
    : item.title;
  const when = tripLine(item);
  const isHotel = (item.type || booking.service) === "hotel";

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
          {paying ? "Processing…" : hasGateway ? `Pay ${total} securely` : `Confirm demo booking · ${total}`}
        </button>
        <div style={{display:'flex',alignItems:'center',gap:8,color:'var(--muted)',fontSize:12,marginTop:14,justifyContent:'center'}} data-testid="pay-note">
          <ShieldCheck size={14} style={{color:'var(--teal)'}}/> {hasGateway ? "Razorpay secured · 256-bit encrypted" : "Demo checkout · no real payment is taken"}
        </div>
      </form>

      <aside className="summary-sticky" data-testid="order-summary">
        <h3>Order summary</h3>
        {item.image && (
          <div style={{borderRadius:12,overflow:'hidden',marginBottom:16}}>
            <img src={item.image} alt="" style={{width:'100%',aspectRatio:isHotel ? '4/3' : '16/7',objectFit:'cover'}} onError={(e) => { e.currentTarget.parentNode.style.display = 'none'; }}/>
          </div>
        )}
        <div style={{fontFamily:'Jost, sans-serif',fontSize:20}} data-testid="summary-title">{heading}</div>
        <div style={{color:'var(--muted)',fontSize:13,marginBottom:14}}>{item.brand}</div>
        {isDemoItem && (
          <div className="dl-note dl-demo" role="note" data-testid="summary-demo">
            Demo booking. Sample data only: no real ticket is issued and no real money is charged.
          </div>
        )}
        <div className="booking-row"><span>Service</span><span style={{textTransform:'capitalize'}}>{booking.service}</span></div>
        {roomName ? <div className="booking-row" data-testid="summary-room"><span>Room</span><span className="dl-row-val">{roomName}</span></div> : null}
        {when ? <div className="booking-row" data-testid="summary-when"><span>{isHotel ? "Stay" : "Trip"}</span><span className="dl-row-val">{when}</span></div> : null}
        {item.cancellation ? <div className="booking-row" data-testid="summary-cancel"><span>Cancellation</span><span className="dl-row-val">{item.cancellation}</span></div> : null}
        <div className="booking-row"><span>Booking ID</span><span style={{fontFamily:MONO}}>{booking.booking_id}</span></div>
        <div className="booking-row"><span>Taxes &amp; fees</span><span>Included</span></div>
        <div className="booking-row"><span>Total</span><span>{total}</span></div>
      </aside>
    </div>
  );
}
