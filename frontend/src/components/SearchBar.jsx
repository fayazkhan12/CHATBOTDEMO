import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plane, Hotel, BusFront, Car, MapPin, CalendarDays, Users, Search } from "lucide-react";
import DestinationInput from "./DestinationInput";
import { dayFromNow, addDays } from "../lib/format";

const SERVICES = [
  { id: "flights", label: "Flights", icon: Plane },
  { id: "hotels", label: "Hotels", icon: Hotel },
  { id: "buses", label: "Buses", icon: BusFront },
  { id: "cabs", label: "Cabs", icon: Car },
];

const MAX_NIGHTS = 30;

// What is wrong with the form, in words the visitor can act on. "" means it is fine to search.
export function formProblem({ service, origin, destination, startDate, endDate }) {
  const hotel = service === "hotels";
  const from = String(origin || "").trim();
  const to = String(destination || "").trim();
  if (!hotel && !from) return "Please enter where you are starting from.";
  if (!to) return hotel ? "Please enter the city you want to stay in." : "Please enter where you want to go.";
  if (!hotel && from.toLowerCase() === to.toLowerCase()) return "From and To are the same place. Please choose two different places.";
  if (!startDate) return hotel ? "Please choose your check-in date." : "Please choose your travel date.";
  if (startDate < dayFromNow(0)) return "That date has already passed. Please choose today or a later date.";
  if (hotel) {
    if (!endDate) return "Please choose your check-out date.";
    if (endDate <= startDate) return "Check-out must be after check-in.";
    if (endDate > addDays(startDate, MAX_NIGHTS)) return `You can search up to ${MAX_NIGHTS} nights at a time.`;
  }
  return "";
}

export default function SearchBar({ initial = {}, onSubmit }) {
  const navigate = useNavigate();

  const [service, setService] = useState(initial.service || "flights");
  const [origin, setOrigin] = useState(initial.origin || "New Delhi");
  const [destination, setDestination] = useState(initial.destination || "Goa");
  const [destinationId, setDestinationId] = useState(initial.destination_id || "");
  const [startDate, setStartDate] = useState(initial.start_date || dayFromNow(1));
  const [endDate, setEndDate] = useState(initial.end_date || dayFromNow(3));
  const [travellers, setTravellers] = useState(Number(initial.travellers) || 2);
  const hotel = service === "hotels";
  const counts = [1, 2, 3, 4, 5, 6];
  if (!counts.includes(travellers)) counts.push(travellers);

  const changeStart = (value) => {
    setStartDate(value);
    // keep the stay valid: check-out is always after check-in
    if (value && (!endDate || endDate <= value)) setEndDate(addDays(value, 1));
  };

  const submit = () => {
    const problem = formProblem({ service, origin, destination, startDate, endDate });
    if (problem) {
      toast.error(problem);
      return;
    }
    const payload = {
      service,
      origin: String(origin).trim(),
      destination: String(destination).trim(),
      start_date: startDate,
      end_date: hotel ? endDate : startDate,
      travellers,
      ...(destinationId ? { destination_id: destinationId } : {}),
    };
    if (onSubmit) return onSubmit(payload);
    const q = new URLSearchParams(payload).toString();
    navigate(`/search?${q}`);
  };

  // Enter in any text or date box searches (buttons and the guest list keep their own Enter behaviour)
  const onKeyDown = (e) => {
    if (e.key !== "Enter") return;
    const tag = e.target && e.target.tagName;
    if (tag === "BUTTON" || tag === "SELECT") return;
    e.preventDefault();
    submit();
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
      <div className={hotel ? "search-fields is-hotel" : "search-fields"} onKeyDown={onKeyDown}>
        {!hotel && (
          <div className="field">
            <div className="field-label"><MapPin size={11}/> From</div>
            <div className="field-input">
              <DestinationInput value={origin} onChange={setOrigin} placeholder="Where from?" testid="origin-input"/>
            </div>
          </div>
        )}
        <div className="field">
          <div className="field-label"><MapPin size={11}/> {hotel ? "Destination" : "To"}</div>
          <div className="field-input">
            <DestinationInput
              value={destination}
              onChange={(v) => { setDestination(v); setDestinationId(""); }}
              onSelect={(r) => setDestinationId(r.supplierLocationId || r.id || "")}
              placeholder={hotel ? "City or area" : "Where to?"}
              testid="destination-input"
            />
          </div>
        </div>
        <div className="field">
          <div className="field-label"><CalendarDays size={11}/> {hotel ? "Check-in / Check-out" : "Date"}</div>
          <div className="field-input">
            <input
              type="date"
              value={startDate}
              min={dayFromNow(0)}
              onChange={(e) => changeStart(e.target.value)}
              aria-label={hotel ? "Check-in date" : "Travel date"}
              data-testid="start-date-input"
            />
            {hotel && (
              <>
                <span className="date-divider">&rarr;</span>
                <input
                  type="date"
                  value={endDate}
                  min={startDate ? addDays(startDate, 1) : dayFromNow(1)}
                  onChange={(e) => setEndDate(e.target.value)}
                  aria-label="Check-out date"
                  data-testid="end-date-input"
                />
              </>
            )}
          </div>
        </div>
        <div className="field">
          <div className="field-label"><Users size={11}/> Travellers</div>
          <div className="field-input">
            <select value={travellers} onChange={(e) => setTravellers(Number(e.target.value))} data-testid="travellers-select">
              {counts.sort((a, b) => a - b).map(n => <option key={n} value={n}>{n} {n === 1 ? "guest" : "guests"}</option>)}
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
