import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Search, X, Zap, ShoppingBag, ChevronRight, Minus, Plus } from "lucide-react";
import { toast } from "sonner";
import { gApi, inr, useCart, addOne, removeOne, addMany } from "../lib/grocery";
import { useAuth } from "../lib/auth";

export function Stepper({ id, qty }) {
  if (!qty) return <button className="gr-add" onClick={() => addOne(id)} data-testid={`gr-add-${id}`}>ADD</button>;
  return (
    <div className="gr-step" data-testid={`gr-step-${id}`}>
      <button onClick={() => removeOne(id)} aria-label="Remove one" data-testid={`gr-minus-${id}`}><Minus size={14} /></button>
      <span data-testid={`gr-qty-${id}`}>{qty}</span>
      <button onClick={() => addOne(id)} disabled={qty >= 10} aria-label="Add one" data-testid={`gr-plus-${id}`}><Plus size={14} /></button>
    </div>
  );
}

function Product({ item, qty }) {
  const off = item.mrp > item.price ? Math.round(((item.mrp - item.price) / item.mrp) * 100) : 0;
  return (
    <div className="gr-card" data-testid={`gr-item-${item.id}`}>
      {off > 0 && <span className="gr-off">{off}% OFF</span>}
      <div className="gr-pic" aria-hidden="true">{item.emoji}</div>
      <div className="gr-name" title={item.name}>{item.name}</div>
      <div className="gr-unit">{item.unit}</div>
      <div className="gr-buy">
        <div className="gr-price"><b>{inr(item.price)}</b>{off > 0 && <s>{inr(item.mrp)}</s>}</div>
        <Stepper id={item.id} qty={qty} />
      </div>
    </div>
  );
}

export default function Grocery() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const cart = useCart();
  const [shelf, setShelf] = useState(null);
  const [failed, setFailed] = useState(false);
  const [q, setQ] = useState(params.get("q") || "");
  const [found, setFound] = useState(null);
  const [cat, setCat] = useState("");
  const [track, setTrack] = useState(null);
  const added = useRef(false);

  const load = useCallback(() => { setFailed(false); gApi.catalog().then(setShelf).catch(() => setFailed(true)); }, []);
  useEffect(load, [load]);

  // a link from the chat: /grocery?add=g-milk:2,g-bread:1
  useEffect(() => {
    if (!shelf || added.current) return;
    const add = params.get("add");
    if (!add) return;
    added.current = true;
    const known = new Set(shelf.items.map((i) => i.id));
    const list = add.split(",").map((p) => { const [id, n] = p.split(":"); return { id, qty: Number(n) || 1 }; }).filter((l) => known.has(l.id));
    if (list.length) { addMany(list); toast.success(`${list.length} item${list.length > 1 ? "s" : ""} added to your cart`); }
    const next = new URLSearchParams(params); next.delete("add"); setParams(next, { replace: true });
  }, [shelf, params, setParams]);

  useEffect(() => {
    const t = q.trim();
    if (!t) { setFound(null); return undefined; }
    let live = true;
    const timer = setTimeout(() => { gApi.search(t).then((r) => { if (live) setFound(r); }).catch(() => { if (live) setFound([]); }); }, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [q]);

  useEffect(() => {
    if (!user) { setTrack(null); return undefined; }
    let live = true;
    gApi.active().then((o) => { if (live) setTrack(o); }).catch(() => {});
    return () => { live = false; };
  }, [user]);

  const byCat = useMemo(() => {
    const m = {};
    (shelf ? shelf.items : []).forEach((i) => { (m[i.category] = m[i.category] || []).push(i); });
    return m;
  }, [shelf]);

  const count = Object.values(cart).reduce((a, b) => a + b, 0);
  const total = shelf ? shelf.items.reduce((a, i) => a + (cart[i.id] || 0) * i.price, 0) : 0;
  const shown = cat ? shelf.categories.filter((c) => c.id === cat) : (shelf ? shelf.categories : []);

  return (
    <div className="gr-page" data-testid="grocery-page">
      <div className="gr-hero">
        <div>
          <h1><Zap size={20} /> Groceries in minutes</h1>
          <p data-testid="gr-eta">Delivery in {shelf ? shelf.delivery.eta : "8-14 min"} · Free delivery above {inr(shelf ? shelf.delivery.free_from : 199)}</p>
        </div>
        <span className="demo-chip">Demo</span>
      </div>

      {track && (
        <Link to={`/grocery/order/${track.order_id}`} className="gr-track" data-testid="gr-track-bar">
          <Zap size={15} /><span><b>Order on its way</b> · {track.state.headline}</span><span className="gr-go">Track <ChevronRight size={14} /></span>
        </Link>
      )}

      <div className="gr-search">
        <Search size={16} />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder='Search "milk", "doodh", "aloo", "maggi"' data-testid="gr-search" aria-label="Search groceries" maxLength={60} />
        {q && <button onClick={() => setQ("")} aria-label="Clear search" data-testid="gr-search-clear"><X size={15} /></button>}
      </div>

      {failed && <div className="empty-state" data-testid="gr-failed"><p>Could not load the store.</p><button className="btn-primary" onClick={load}>Try again</button></div>}
      {!shelf && !failed && <div className="empty-state" data-testid="gr-loading">Opening the store...</div>}

      {shelf && found === null && (
        <div className="gr-cats" data-testid="gr-cats">
          <button className={!cat ? "on" : ""} onClick={() => setCat("")} data-testid="gr-cat-all">All</button>
          {shelf.categories.map((c) => (
            <button key={c.id} className={cat === c.id ? "on" : ""} onClick={() => setCat(c.id)} data-testid={`gr-cat-${c.id}`}><span aria-hidden="true">{c.emoji}</span> {c.name}</button>
          ))}
        </div>
      )}

      {shelf && found !== null && (
        found.length ? (
          <section data-testid="gr-results">
            <h2 className="gr-h">{found.length} result{found.length > 1 ? "s" : ""} for "{q.trim()}"</h2>
            <div className="gr-grid">{found.map((i) => <Product key={i.id} item={i} qty={cart[i.id] || 0} />)}</div>
          </section>
        ) : (
          <div className="empty-state" data-testid="gr-none"><p>We could not find "{q.trim()}". Try another word, like "milk" or "atta".</p></div>
        )
      )}

      {shelf && found === null && shown.map((c) => (
        <section key={c.id} data-testid={`gr-section-${c.id}`}>
          <h2 className="gr-h"><span aria-hidden="true">{c.emoji}</span> {c.name}</h2>
          <div className="gr-grid">{(byCat[c.id] || []).map((i) => <Product key={i.id} item={i} qty={cart[i.id] || 0} />)}</div>
        </section>
      ))}

      {count > 0 && (
        <button className="gr-cartbar" onClick={() => navigate("/grocery/cart")} data-testid="gr-cartbar">
          <ShoppingBag size={18} />
          <span><b>{count} item{count > 1 ? "s" : ""}</b> · {inr(total)}</span>
          <span className="gr-go">View cart <ChevronRight size={16} /></span>
        </button>
      )}
    </div>
  );
}
