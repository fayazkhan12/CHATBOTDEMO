import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plane, Hotel, BusFront, Car, MapPin, CalendarDays, Users, Search, Clock } from "lucide-react";
import DestinationInput from "./DestinationInput";
import PlaceInput from "./PlaceInput";
import { boxLimits, boxToWhen, rideUrl, whenToBox } from "../lib/rides";
import { dayFromNow, addDays, plural, readOccupancy } from "../lib/format";

const SERVICES = [
  { id: "flights", label: "Flights", icon: Plane },
  { id: "hotels", label: "Hotels", icon: Hotel },
  { id: "buses", label: "Buses", icon: BusFront },
  { id: "cabs", label: "Rides", icon: Car },
];

const MAX_NIGHTS = 30;

// What is wrong with the form, in words the visitor can act on. "" means it is fine to search.
export function formProblem({ service, origin, destination, startDate, endDate, rooms, adults, children, childAges }) {
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
    const roomCount = Number(rooms) || 1;
    const adultCount = Number(adults) || 0;
    const kids = Number(children) || 0;
    if (adultCount && roomCount > adultCount) return "Every room needs at least one adult. Choose fewer rooms or more adults.";
    if (kids > 0) {
      const ages = (childAges || []).slice(0, kids);
      const bad = (a) => a === "" || a === null || a === undefined || !Number.isInteger(Number(a)) || Number(a) < 0 || Number(a) > 17;
      if (ages.length < kids || ages.some(bad)) return "Please choose the age of each child.";
    }
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
  const occ = readOccupancy(initial);
  const [travellers, setTravellers] = useState(Number(initial.travellers) || 2);   // hotels: the adults
  const [rooms, setRooms] = useState(occ.rooms);
  const [children, setChildren] = useState(occ.children);
  const [childAges, setChildAges] = useState(occ.childAges.map(String));
  const hotel = service === "hotels";
  const ride = service === "cabs";
  // rides: bike, auto and cab have their own screen; this tab only collects the two places and the time
  const [pickup, setPickup] = useState(null);
  const [drop, setDrop] = useState(null);
  const [rideWhen, setRideWhen] = useState("now");
  const counts = hotel ? [1, 2, 3, 4, 5, 6, 7, 8, 9, 10] : [1, 2, 3, 4, 5, 6];
  if (!counts.includes(travellers)) counts.push(travellers);

  // every room has at least one adult, so the two numbers move together
  const changeRooms = (n) => { setRooms(n); if (travellers < n) setTravellers(n); };
  const changeAdults = (n) => { setTravellers(n); if (rooms > n) setRooms(n); };
  const changeChildren = (n) => { setChildren(n); setChildAges((old) => Array.from({ length: n }, (_, i) => old[i] ?? "")); };
  const changeAge = (i, value) => setChildAges((old) => Object.assign([...old], { [i]: value }));

  const changeStart = (value) => {
    setStartDate(value);
    // keep the stay valid: check-out is always after check-in
    if (value && (!endDate || endDate <= value)) setEndDate(addDays(value, 1));
  };

  const submit = () => {
    if (ride) {
      if (!pickup || !drop) { toast.error(!pickup ? "Please choose the pickup place." : "Please choose where you want to go."); return; }
      navigate(rideUrl({ pickup, drop, when: rideWhen }));
      return;
    }
    const problem = formProblem({ service, origin, destination, startDate, endDate, rooms, adults: travellers, children, childAges });
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
      ...(hotel && rooms > 1 ? { rooms } : {}),
      ...(hotel && children > 0 ? { children, child_ages: childAges.slice(0, children).join(",") } : {}),
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
      {ride && (
        <div className="search-fields is-ride" data-testid="ride-search-fields">
          <div className="field">
            <PlaceInput label="Pickup" tone="pickup" value={pickup} onChange={setPickup} allowCurrent placeholder="Pickup place" testid="ride-pickup-input" />
          </div>
          <div className="field">
            <PlaceInput label="Drop" tone="drop" value={drop} onChange={setDrop} near={pickup} placeholder="Where to?" testid="ride-drop-input" />
          </div>
          <div className="field">
            <div className="field-label"><Clock size={11}/> When</div>
            <div className="field-input">
              <select value={rideWhen === "now" ? "now" : "later"} onChange={(e) => {
                if (e.target.value === "now") { setRideWhen("now"); return; }
                const d = new Date(Date.now() + 60 * 60000); d.setMinutes(Math.ceil(d.getMinutes() / 5) * 5, 0, 0);
                const p = (n) => String(n).padStart(2, "0");
                setRideWhen(boxToWhen(`${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`));
              }} aria-label="When" data-testid="ride-when-select">
                <option value="now">Now</option>
                <option value="later">Schedule</option>
              </select>
              {rideWhen !== "now" && (
                <input type="datetime-local" min={boxLimits().min} max={boxLimits().max} value={whenToBox(rideWhen)} onChange={(e) => e.target.value && setRideWhen(boxToWhen(e.target.value))} aria-label="Pickup time" data-testid="ride-when-input" />
              )}
            </div>
          </div>
          <button className="search-submit" onClick={submit} data-testid="search-submit"><Search size={18}/> See fares</button>
        </div>
      )}
      <div className={hotel ? "search-fields is-hotel" : "search-fields"} onKeyDown={onKeyDown} hidden={ride}>
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
        {hotel ? (
          <div className="field field-guests">
            <div className="field-label"><Users size={11}/> Rooms &amp; guests</div>
            <div className="field-input guest-row">
              <select value={rooms} onChange={(e) => changeRooms(Number(e.target.value))} aria-label="Rooms" data-testid="rooms-select">
                {[1, 2, 3, 4, 5].map(n => <option key={n} value={n}>{plural(n, "room")}</option>)}
              </select>
              <select value={travellers} onChange={(e) => changeAdults(Number(e.target.value))} aria-label="Adults" data-testid="travellers-select">
                {counts.sort((a, b) => a - b).map(n => <option key={n} value={n}>{plural(n, "adult")}</option>)}
              </select>
              <select value={children} onChange={(e) => changeChildren(Number(e.target.value))} aria-label="Children" data-testid="children-select">
                {[0, 1, 2, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n === 0 ? "No children" : plural(n, "child", "children")}</option>)}
              </select>
            </div>
            {children > 0 && (
              <div className="child-ages" data-testid="child-ages">
                {Array.from({ length: children }, (_, i) => (
                  <select key={i} value={childAges[i] ?? ""} onChange={(e) => changeAge(i, e.target.value)} aria-label={`Age of child ${i + 1}`} data-testid={`child-age-${i}`}>
                    <option value="" disabled>{`Child ${i + 1} age`}</option>
                    <option value="0">Under 1 year</option>
                    {Array.from({ length: 17 }, (_, k) => k + 1).map(a => <option key={a} value={a}>{plural(a, "year")}</option>)}
                  </select>
                ))}
              </div>
            )}
          </div>
        ) : (
          <div className="field">
            <div className="field-label"><Users size={11}/> Travellers</div>
            <div className="field-input">
              <select value={travellers} onChange={(e) => setTravellers(Number(e.target.value))} data-testid="travellers-select">
                {counts.sort((a, b) => a - b).map(n => <option key={n} value={n}>{n} {n === 1 ? "guest" : "guests"}</option>)}
              </select>
            </div>
          </div>
        )}
        <button className="search-submit" onClick={submit} data-testid="search-submit">
          <Search size={18}/> Search
        </button>
      </div>
    </div>
  );
}
