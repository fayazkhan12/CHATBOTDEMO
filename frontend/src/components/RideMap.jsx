import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { vehicleSvg } from "../lib/rideicons";

// A map for the ride screens (OpenStreetMap tiles through Leaflet). Draws the pickup, the drop, the route and,
// while a ride is going on, the captain's vehicle. If the tiles cannot be loaded the route and pins still show
// on a plain grid, so the screen is never empty.
const ORANGE = "#E8820C";

const pinIcon = (cls) => L.divIcon({ className: "ride-pin-wrap", html: `<span class="ride-pin ${cls}"><i></i></span>`, iconSize: [22, 22], iconAnchor: [11, 11] });
const vehicleIcon = (kind) => L.divIcon({ className: "ride-vehicle-wrap", html: `<span class="ride-vehicle">${vehicleSvg(kind, 20)}</span>`, iconSize: [36, 36], iconAnchor: [18, 18] });

const valid = (p) => p && Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lng)) && p.lat !== null && p.lng !== null;
const ll = (p) => [Number(p.lat), Number(p.lng)];

function tip(text) {
  const el = document.createElement("span");
  el.textContent = String(text || "");
  return el;
}

export default function RideMap({ pickup, drop, route, vehicle, vehicleKind = "cab", follow = false, className = "", label = "Ride map" }) {
  const el = useRef(null);
  const map = useRef(null);
  const layers = useRef({});
  const fitted = useRef("");
  const [tilesFailed, setTilesFailed] = useState(false);

  // create / destroy the map
  useEffect(() => {
    const m = L.map(el.current, { zoomControl: false, attributionControl: true, scrollWheelZoom: true, tap: true }).setView([22.9, 79.5], 4);
    // top right: on a laptop the map fills the right-hand column down to the corner of the window, which is where the
    // floating voice button sits, so zoom buttons in the bottom-right corner would be hidden under it
    L.control.zoom({ position: "topright" }).addTo(m);
    let errors = 0;
    const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a>',
    }).addTo(m);
    tiles.on("tileerror", () => { errors += 1; if (errors >= 4) setTilesFailed(true); });
    tiles.on("tileload", () => { if (errors) { errors = 0; setTilesFailed(false); } });
    map.current = m;
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => m.invalidateSize()) : null;
    if (ro) ro.observe(el.current);
    return () => {
      if (ro) ro.disconnect();
      m.remove();
      map.current = null;
      layers.current = {};
      fitted.current = "";
    };
  }, []);

  // pickup, drop, route
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const L_ = layers.current;
    const put = (key, p, cls, text) => {
      if (L_[key]) { m.removeLayer(L_[key]); L_[key] = null; }
      if (valid(p)) {
        L_[key] = L.marker(ll(p), { icon: pinIcon(cls), keyboard: false, title: text }).addTo(m);
        L_[key].bindTooltip(tip(`${text}: ${p.name || ""}`), { direction: "top", offset: [0, -10] });
      }
    };
    put("pickup", pickup, "pickup", "Pickup");
    put("drop", drop, "drop", "Drop");
    if (L_.casing) { m.removeLayer(L_.casing); L_.casing = null; }
    if (L_.line) { m.removeLayer(L_.line); L_.line = null; }
    const pts = Array.isArray(route) ? route.filter((p) => Array.isArray(p) && p.length === 2) : [];
    if (pts.length >= 2) {
      L_.casing = L.polyline(pts, { color: "#fff", weight: 9, opacity: 0.95, lineCap: "round", lineJoin: "round", interactive: false }).addTo(m);
      L_.line = L.polyline(pts, { color: ORANGE, weight: 5, opacity: 1, lineCap: "round", lineJoin: "round", interactive: false }).addTo(m);
    }
    const key = [pickup && pickup.lat, pickup && pickup.lng, drop && drop.lat, drop && drop.lng, pts.length].join("|");
    if (fitted.current !== key) {
      fitted.current = key;
      const all = [];
      if (valid(pickup)) all.push(ll(pickup));
      if (valid(drop)) all.push(ll(drop));
      pts.forEach((p) => all.push(p));
      if (all.length === 1) m.setView(all[0], 15);
      else if (all.length > 1) m.fitBounds(L.latLngBounds(all), { padding: [44, 44], maxZoom: 16 });
    }
  }, [pickup, drop, route]);

  // the captain's vehicle
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    const L_ = layers.current;
    if (!vehicle || !Array.isArray(vehicle)) {
      if (L_.vehicle) { m.removeLayer(L_.vehicle); L_.vehicle = null; }
      return;
    }
    if (!L_.vehicle) L_.vehicle = L.marker(vehicle, { icon: vehicleIcon(vehicleKind), keyboard: false, zIndexOffset: 1000, interactive: false }).addTo(m);
    else L_.vehicle.setLatLng(vehicle);
    if (follow && !m.getBounds().pad(-0.18).contains(vehicle)) {
      const all = [vehicle];
      if (valid(pickup)) all.push(ll(pickup));
      if (valid(drop)) all.push(ll(drop));
      m.fitBounds(L.latLngBounds(all), { padding: [44, 44], maxZoom: 16, animate: true });
    }
  }, [vehicle, vehicleKind, follow, pickup, drop]);

  return (
    <div className={`ride-map ${className}`} role="img" aria-label={label} data-testid="ride-map">
      <div ref={el} className="ride-map-canvas" />
      {tilesFailed && <div className="ride-map-note" role="status">Map pictures could not load. The route is still shown.</div>}
    </div>
  );
}
