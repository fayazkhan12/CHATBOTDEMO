import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, Check, Bike, Phone } from "lucide-react";
import { toast } from "sonner";
import { gApi, inr, errorText } from "../lib/grocery";

export default function GroceryOrder() {
  const { id } = useParams();
  const [o, setO] = useState(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { setO(await gApi.get(id)); setErr(""); } catch (e) { setErr(errorText(e, "We could not load this order.")); }
  }, [id]);

  useEffect(() => {
    load();
    const t = setInterval(() => { if (!document.hidden) load(); }, 4000);
    return () => clearInterval(t);
  }, [load]);

  const cancel = async () => {
    if (busy) return;
    setBusy(true);
    try { setO(await gApi.cancel(id, "Changed my mind")); toast.success("Order cancelled"); } catch (e) { toast.error(errorText(e)); } finally { setBusy(false); }
  };

  if (err && !o) return <div className="gr-page"><div className="empty-state" data-testid="gr-order-error"><p>{err}</p><Link to="/grocery" className="btn-primary">Back to the store</Link></div></div>;
  if (!o) return <div className="gr-page"><div className="empty-state">Loading your order...</div></div>;

  const st = o.state;
  const over = st.stage === "delivered" || st.stage === "cancelled";
  return (
    <div className="gr-page gr-orderpage" data-testid="gr-order">
      <Link to="/grocery" className="gr-back"><ArrowLeft size={15} /> Back to the store</Link>
      <section className={`gr-box gr-status ${st.stage}`}>
        <small>Order {o.order_id} <span className="demo-chip">Demo</span></small>
        <h1 data-testid="gr-headline">{st.headline}</h1>
        {!over && <div className="gr-bar" aria-hidden="true"><i style={{ width: `${Math.round(st.progress * 100)}%` }} /></div>}
        {st.stage === "on_the_way" && <p data-testid="gr-eta-left">Arriving in about {Math.max(1, st.eta_left_min)} min</p>}
        {o.delivery_otp && <p className="gr-otp" data-testid="gr-otp">Delivery code: <b>{o.delivery_otp}</b> (tell it to the rider)</p>}
        {st.stage === "cancelled" && o.cancel && <p data-testid="gr-cancelled">{o.cancel.refund}</p>}
      </section>

      {st.stage !== "cancelled" && (
        <section className="gr-box">
          <ol className="gr-steps" data-testid="gr-steps">
            {o.steps.map((s) => <li key={s.key} className={s.done ? "done" : ""} data-testid={`gr-step-${s.key}`}><span>{s.done ? <Check size={13} /> : null}</span>{s.label}</li>)}
          </ol>
        </section>
      )}

      {o.rider && st.stage !== "cancelled" && (
        <section className="gr-box gr-rider" data-testid="gr-rider">
          <Bike size={22} />
          <div><b>{o.rider.name}</b><small>{o.rider.vehicle} · {o.rider.rating} stars</small></div>
          <span className="gr-phone"><Phone size={14} /> {o.rider.phone}</span>
        </section>
      )}

      <section className="gr-box">
        <h2 className="gr-h2">Delivering to</h2>
        <p className="gr-addr" data-testid="gr-address">{o.address.name} · {o.address.phone}<br />{o.address.line}{o.address.landmark ? `, near ${o.address.landmark}` : ""} - {o.address.pincode}</p>
      </section>

      <section className="gr-box">
        <h2 className="gr-h2">{o.items.length} item{o.items.length > 1 ? "s" : ""}</h2>
        {o.items.map((l) => <div className="gr-line ro" key={l.id}><span className="gr-pic sm" aria-hidden="true">{l.emoji}</span><div className="gr-lname"><b>{l.name}</b><small>{l.unit} x {l.qty}</small></div><span className="gr-ltotal">{inr(l.line_total)}</span></div>)}
        <dl className="gr-billro">
          <div><dt>Items total</dt><dd>{inr(o.bill.items_total)}</dd></div>
          <div><dt>Delivery and fees</dt><dd>{inr(o.bill.delivery_fee + o.bill.small_cart_fee + o.bill.handling_fee)}</dd></div>
          {o.bill.discount > 0 && <div><dt>Coupon {o.bill.coupon}</dt><dd>-{inr(o.bill.discount)}</dd></div>}
          <div className="tot"><dt>{o.payment.method === "cod" ? "To pay on delivery" : "Paid (demo)"}</dt><dd data-testid="gr-o-total">{inr(o.bill.total)}</dd></div>
        </dl>
      </section>

      {st.can_cancel && <button className="btn-ghost gr-cancel" onClick={cancel} disabled={busy} data-testid="gr-cancel">Cancel order</button>}
      {over && <Link to="/grocery" className="btn-primary" data-testid="gr-again">Order again</Link>}
      <small className="gr-demo">{o.note}</small>
    </div>
  );
}
