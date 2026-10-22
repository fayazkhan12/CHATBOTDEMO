import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Plane, Hotel, BusFront, Car, MapPin, CalendarDays, Users, Search } from "lucide-react";
import DestinationInput from "./DestinationInput";

const SERVICES = [
  { id: "flights", label: "Flights", icon: Plane },
  { id: "hotels", label: "Hotels", icon: Hotel },
  { id: "buses", label: "Buses", icon: BusFront },
  { id: "cabs", label: "Cabs", icon: Car },
];

export default function SearchBar({ initial = {}, onSubmit }) {
  const navigate = useNavigate();
  const today = new Date();
  const tmr = new Date(today.getTime() + 86400000);
  const nextWeek = new Date(today.getTime() + 7 * 86400000);
  const fmt = (d) => d.toISOString().slice(0, 10);

  const [service, setService] = useState(initial.service || "flights");
  const [origin, setOrigin] = useState(initial.origin || "New Delhi");
  const [destination, setDestination] = useState(initial.destination || "Goa");
  const [destinationId, setDestinationId] = useState(initial.destination_id || "");
  const [startDate, setStartDate] = useState(initial.start_date || fmt(tmr));
  const [endDate, setEndDate] = useState(initial.end_date || fmt(nextWeek));
  const [travellers, setTravellers] = useState(initial.travellers || 2);

  const submit = () => {
    const payload = {
      service, origin, destination, start_date: startDate, end_date: endDate, travellers,
      ...(destinationId ? { destination_id: destinationId } : {}),
    };
    if (onSubmit) return onSubmit(payload);
    const q = new URLSearchParams(payload).toString();
    navigate(`/search?${q}`);
  };

  return (
    <div className="search-shell" data-testid="search-shell">
      <div className="service-tabs" role="tablist">
        {SERVICES.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={service === id}
            className={service === id ? "service-tab active" : "service-tab"}
            onClick={() => setService(id)}
            data-testid={`${id}-service-tab`}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>
      <div className="search-fields">
        <div className="field">
          <div className="field-label"><MapPin size={11}/> {service === "hotels" ? "City" : "From"}</div>
          <div className="field-input">
            <DestinationInput value={origin} onChange={setOrigin} placeholder="Origin" testid="origin-input"/>
          </div>
        </div>
        <div className="field">
          <div className="field-label"><MapPin size={11}/> {service === "hotels" ? "Destination" : "To"}</div>
          <div className="field-input">
            <DestinationInput value={destination} onChange={(v) => { setDestination(v); setDestinationId(""); }} onSelect={(r) => setDestinationId(r.supplierLocationId || r.id || "")} placeholder="Destination" testid="destination-input"/>
          </div>
        </div>
        <div className="field">
          <div className="field-label"><CalendarDays size={11}/> Dates</div>
          <div className="field-input">
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} data-testid="start-date-input"/>
            <span className="date-divider">→</span>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} data-testid="end-date-input"/>
          </div>
        </div>
        <div className="field">
          <div className="field-label"><Users size={11}/> Travellers</div>
          <div className="field-input">
            <select value={travellers} onChange={(e) => setTravellers(Number(e.target.value))} data-testid="travellers-select">
              {[1,2,3,4,5,6].map(n => <option key={n} value={n}>{n} {n === 1 ? "guest" : "guests"}</option>)}
            </select>
          </div>
        </div>
        <button className="search-submit" onClick={submit} data-testid="search-submit">
          <Search size={18}/> Search
        </button>
      </div>
    </div>
  );
}
