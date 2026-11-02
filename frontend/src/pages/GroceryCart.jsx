import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, Tag, ShoppingBag } from "lucide-react";
import { toast } from "sonner";
import { gApi, inr, useCart, cartLines, clearCart, errorText, savedAddress, saveAddress } from "../lib/grocery";
import { validateName, validatePhone, validateAddress } from "../lib/validate";
import { useAuth } from "../lib/auth";
import { Stepper } from "./Grocery";

export default function GroceryCart() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const cart = useCart();
  const [bill, setBill] = useState(null);
  const [coupon, setCoupon] = useState("");
  const [applied, setApplied] = useState("");
  const [busy, setBusy] = useState(false);
  const [pay, setPay] = useState("cod");
  const saved = savedAddress();
  const [a, setA] = useState({ name: saved.name || "", phone: saved.phone || "", line: saved.line || "", landmark: saved.landmark || "", pincode: saved.pincode || "" });
  const [errs, setErrs] = useState({});
  const ids = Object.keys(cart).sort().join(",");

  useEffect(() => { if (user && !a.name) setA((p) => ({ ...p, name: user.name && !validateName(user.name) ? user.name : "" })); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const lines = cartLines();
    if (!lines.length) { setBill(null); return undefined; }
    let live = true;
    gApi.quote(lines, applied).then((b) => { if (live) setBill(b); }).catch((e) => { if (live) { setBill(null); toast.error(errorText(e)); } });
    return () => { live = false; };
  }, [cart, applied]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (k) => (e) => { setA((p) => ({ ...p, [k]: e.target.value })); setErrs((p) => ({ ...p, [k]: "" })); };

  const place = async () => {
    if (!bill || busy) return;
    const e = {
      name: validateName(a.name) ? "Please enter your full name." : "",
      phone: validatePhone(a.phone),
      line: !a.line.trim() ? "Please enter your house number, street and area." : validateAddress(a.line),
      pincode: /^\d{6}$/.test(a.pincode.trim()) ? "" : "Enter a 6 digit pincode.",
    };
    setErrs(e);
    if (Object.values(e).some(Boolean)) { toast.error("Please check your delivery details."); return; }
    if (!user) { navigate(`/login?redirect=${encodeURIComponent("/grocery/cart")}`); return; }
    if (bill.items_total < bill.min_order) { toast.error(`The smallest order is ${inr(bill.min_order)}.`); return; }
    setBusy(true);
    try {
      const o = await gApi.order({ items: cartLines(), coupon: applied || undefined, address: { ...a, name: a.name.trim(), pincode: a.pincode.trim() }, payment: pay });
      saveAddress(a);
      clearCart();
      navigate(`/grocery/order/${o.order_id}`);
    } catch (err) {
      toast.error(errorText(err));
    } finally { setBusy(false); }
  };

  const applyCoupon = () => { setApplied(coupon.trim().toUpperCase()); };

  if (!ids) {
    return (
      <div className="gr-page" data-testid="gr-cart-empty">
        <div className="empty-state"><ShoppingBag size={28} /><p>Your cart is empty.</p><Link to="/grocery" className="btn-primary" data-testid="gr-shop">Start shopping</Link></div>
      </div>
    );
  }

  const lines = bill ? bill.lines : [];
  const need = bill ? Math.max(0, bill.free_delivery_from - bill.items_total) : 0;
  return (
    <div className="gr-page gr-cartpage" data-testid="gr-cart">
      <Link to="/grocery" className="gr-back"><ArrowLeft size={15} /> Keep shopping</Link>
      <h1 className="gr-title">Your cart <span className="demo-chip">Demo</span></h1>
      <div className="gr-cols">
        <div>
          <section className="gr-box">
            {need > 0 && bill && <div className="gr-nudge" data-testid="gr-nudge">Add {inr(need)} more for free delivery</div>}
            {bill && need === 0 && <div className="gr-nudge ok" data-testid="gr-free">You get free delivery</div>}
            {lines.map((l) => (
              <div className="gr-line" key={l.id} data-testid={`gr-line-${l.id}`}>
                <span className="gr-pic sm" aria-hidden="true">{l.emoji}</span>
                <div className="gr-lname"><b>{l.name}</b><small>{l.unit} · {inr(l.price)}</small></div>
                <Stepper id={l.id} qty={cart[l.id] || 0} />
                <span className="gr-ltotal">{inr(l.line_total)}</span>
              </div>
            ))}
          </section>

          <section className="gr-box">
            <h2 className="gr-h2">Delivery details</h2>
            <div className="gr-form">
              <label>Full name<input value={a.name} onChange={set("name")} autoComplete="name" data-testid="gr-name" maxLength={60} />{errs.name && <em data-testid="gr-err-name">{errs.name}</em>}</label>
              <label>Mobile number<input value={a.phone} onChange={set("phone")} inputMode="tel" autoComplete="tel" data-testid="gr-phone" maxLength={16} />{errs.phone && <em data-testid="gr-err-phone">{errs.phone}</em>}</label>
              <label className="wide">House no., street, area<input value={a.line} onChange={set("line")} autoComplete="street-address" data-testid="gr-line-input" maxLength={160} />{errs.line && <em data-testid="gr-err-line">{errs.line}</em>}</label>
              <label>Landmark (optional)<input value={a.landmark} onChange={set("landmark")} data-testid="gr-landmark" maxLength={80} /></label>
              <label>Pincode<input value={a.pincode} onChange={set("pincode")} inputMode="numeric" autoComplete="postal-code" data-testid="gr-pincode" maxLength={6} />{errs.pincode && <em data-testid="gr-err-pincode">{errs.pincode}</em>}</label>
            </div>
          </section>
        </div>

        <aside className="gr-box gr-bill" data-testid="gr-bill">
          <h2 className="gr-h2">Bill details</h2>
          <div className="gr-coupon">
            <Tag size={15} />
            <input value={coupon} onChange={(e) => setCoupon(e.target.value)} placeholder="Coupon code (try DEMO50)" data-testid="gr-coupon" maxLength={20} />
            <button className="btn-ghost" onClick={applyCoupon} data-testid="gr-apply">Apply</button>
          </div>
          {bill && bill.coupon_note && <small className={bill.discount ? "gr-ok" : "gr-warn"} data-testid="gr-coupon-note">{bill.coupon_note}</small>}
          {bill ? (
            <dl>
              <div><dt>Items total</dt><dd data-testid="gr-b-items">{inr(bill.items_total)}</dd></div>
              <div><dt>Delivery fee</dt><dd data-testid="gr-b-delivery">{bill.delivery_fee ? inr(bill.delivery_fee) : "FREE"}</dd></div>
              {bill.small_cart_fee > 0 && <div><dt>Small cart fee</dt><dd>{inr(bill.small_cart_fee)}</dd></div>}
              <div><dt>Handling fee</dt><dd>{inr(bill.handling_fee)}</dd></div>
              {bill.discount > 0 && <div><dt>Coupon</dt><dd className="gr-ok">-{inr(bill.discount)}</dd></div>}
              <div className="tot"><dt>To pay</dt><dd data-testid="gr-b-total">{inr(bill.total)}</dd></div>
            </dl>
          ) : <small>Working out your bill...</small>}
          {bill && bill.savings > 0 && <div className="gr-save" data-testid="gr-savings">You save {inr(bill.savings)} on this order</div>}
          <div className="gr-pay" role="radiogroup" aria-label="Payment">
            <label className={pay === "cod" ? "on" : ""}><input type="radio" name="pay" checked={pay === "cod"} onChange={() => setPay("cod")} data-testid="gr-pay-cod" /> Cash on delivery</label>
            <label className={pay === "upi" ? "on" : ""}><input type="radio" name="pay" checked={pay === "upi"} onChange={() => setPay("upi")} data-testid="gr-pay-upi" /> UPI (demo, nothing is charged)</label>
          </div>
          <button className="btn-primary gr-place" onClick={place} disabled={!bill || busy} data-testid="gr-place">
            {busy ? "Placing order..." : user ? `Place order · ${bill ? inr(bill.total) : ""}` : "Log in to place order"}
          </button>
          <small className="gr-demo">Demo order: no shop packs anything, no rider comes and nothing is charged.</small>
        </aside>
      </div>
    </div>
  );
}
