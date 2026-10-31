import { useEffect, useId, useRef, useState } from "react";
import { Crosshair, Loader2, MapPin, Plane, TrainFront, BusFront, Landmark, X } from "lucide-react";
import { toast } from "sonner";
import { rideApi, hasPoint } from "../lib/rides";

const KIND_ICON = { airport: Plane, station: TrainFront, bus: BusFront, landmark: Landmark };

export function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) return reject(new Error("unsupported"));
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ name: "Current location", lat: p.coords.latitude, lng: p.coords.longitude }),
      (e) => reject(e),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 60000 },
    );
  });
}

const geoMessage = (e) => (e && e.code === 1
  ? "Location is blocked for this site. Allow it in your browser, or type the pickup place."
  : "Could not get your location. Type the pickup place instead.");

// A place box with suggestions: type a landmark, station or area, or use the current location (pickup).
export default function PlaceInput({ label, value, onChange, near, allowCurrent = false, placeholder, tone = "pickup", testid }) {
  const id = useId();
  const [text, setText] = useState(value ? value.name : "");
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [active, setActive] = useState(-1);
  const [locating, setLocating] = useState(false);
  const focused = useRef(false);
  const seq = useRef(0);
  const timer = useRef(null);

  // the place was changed from outside (swap, a link, "current location")
  useEffect(() => {
    if (!focused.current) setText(value ? value.name : "");
  }, [value]);

  const load = (q) => {
    const mine = ++seq.current;
    setBusy(true);
    rideApi.places(q, near && hasPoint(near) ? near : null)
      .then((r) => { if (mine === seq.current) { setItems(r); setActive(-1); } })
      .catch(() => { if (mine === seq.current) setItems([]); })
      .finally(() => { if (mine === seq.current) setBusy(false); });
  };

  const type = (v) => {
    setText(v);
    setOpen(true);
    if (value) onChange(null);                     // editing a chosen place clears it
    clearTimeout(timer.current);
    if (v.trim().length < 2) { seq.current += 1; setItems([]); setBusy(false); if (!v.trim() && near && hasPoint(near)) timer.current = setTimeout(() => load(""), 150); return; }
    timer.current = setTimeout(() => load(v.trim()), 220);
  };
  useEffect(() => () => clearTimeout(timer.current), []);

  const choose = (p) => {
    onChange({ name: p.name, lat: p.lat, lng: p.lng });
    setText(p.name);
    setOpen(false);
    setItems([]);
  };

  const fillHere = async () => {
    setLocating(true);
    try {
      const here = await getPosition();
      choose(here);
    } catch (e) {
      toast.error(geoMessage(e));
    } finally {
      setLocating(false);
    }
  };

  const rows = [];
  if (allowCurrent && !value && text.trim().length < 2) rows.push({ current: true });
  // while the answer for the latest keystroke is on its way, only the older suggestions that still fit are kept
  const typed = text.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const fits = (p) => { const hay = `${p.name} ${p.sub}`.toLowerCase(); return typed.every((t) => hay.includes(t)); };
  (busy && typed.length ? items.filter(fits) : items).forEach((p) => rows.push(p));

  const onKey = (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setActive((a) => Math.min(rows.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Escape") { setOpen(false); }
    else if (e.key === "Enter") {
      const row = rows[active] || (rows.length === 1 || (items.length && active < 0) ? rows.find((r) => !r.current) : null);
      if (row) { e.preventDefault(); if (row.current) fillHere(); else choose(row); }
    }
  };

  return (
    <div className={`place-input tone-${tone}`}>
      <label className="place-label" htmlFor={id}>{label}</label>
      <div className="place-box">
        <span className="place-dot" aria-hidden="true" />
        <input
          id={id}
          value={text}
          placeholder={placeholder}
          autoComplete="off"
          role="combobox"
          aria-expanded={open && rows.length > 0}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          onChange={(e) => type(e.target.value)}
          onFocus={() => { focused.current = true; setOpen(true); if (!value && text.trim().length < 2 && near && hasPoint(near)) load(""); }}
          onBlur={() => { focused.current = false; setTimeout(() => setOpen(false), 160); if (value) setText(value.name); }}
          onKeyDown={onKey}
          data-testid={testid}
        />
        {(busy || locating) && <Loader2 size={15} className="spin place-spin" aria-hidden="true" />}
        {text && !busy && !locating && (
          <button type="button" className="place-clear" aria-label={`Clear ${label}`} onMouseDown={(e) => e.preventDefault()} onClick={() => { setText(""); onChange(null); setItems([]); }}>
            <X size={14} />
          </button>
        )}
      </div>
      {open && rows.length > 0 && (
        <ul className="place-list" id={`${id}-list`} role="listbox" data-testid={`${testid}-list`}>
          {rows.map((r, i) => {
            if (r.current) {
              return (
                <li key="current" role="option" aria-selected={i === active} className={i === active ? "place-row active" : "place-row"}
                  onMouseDown={(e) => { e.preventDefault(); fillHere(); }} data-testid={`${testid}-current`}>
                  <Crosshair size={16} /><span><b>Use my current location</b><small>Your browser will ask for permission</small></span>
                </li>
              );
            }
            const Icon = KIND_ICON[r.kind] || MapPin;
            return (
              <li key={r.id} role="option" aria-selected={i === active} className={i === active ? "place-row active" : "place-row"}
                onMouseDown={(e) => { e.preventDefault(); choose(r); }} data-testid={`${testid}-opt`}>
                <Icon size={16} /><span><b>{r.name}</b><small>{r.sub}</small></span>
              </li>
            );
          })}
        </ul>
      )}
      {open && !busy && text.trim().length >= 2 && items.length === 0 && (
        <div className="place-empty" role="status">No place found. Try a landmark, station or area with the city name.</div>
      )}
    </div>
  );
}
