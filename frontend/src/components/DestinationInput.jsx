import { useEffect, useRef, useState } from "react";
import { Loader2, MapPin, Plane, Hotel, Building2 } from "lucide-react";
import { http } from "../lib/api";

const typeIcon = { city: MapPin, airport: Plane, hotel: Hotel, multiCity: Building2, trainStation: MapPin };

export default function DestinationInput({ value, onChange, onSelect, placeholder = "City, airport or landmark…", testid }) {
  const [results, setResults] = useState([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef(null);
  const blurTimerRef = useRef(null);

  useEffect(() => {
    if (!value || value.length < 2) { setResults([]); return; }
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const { data } = await http.get(`/destinations/autocomplete?q=${encodeURIComponent(value)}`);
        setResults(data.results || []);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => debounceRef.current && clearTimeout(debounceRef.current);
  }, [value]);

  const pick = (r) => {
    onChange(r.label);
    onSelect?.(r);
    setOpen(false);
  };

  return (
    <div className="dest-input-wrap">
      <input
        value={value}
        onChange={(e) => { onChange(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => { blurTimerRef.current = setTimeout(() => setOpen(false), 180); }}
        placeholder={placeholder}
        data-testid={testid}
      />
      {open && (results.length > 0 || loading) && (
        <div className="dest-dropdown" data-testid={`${testid}-dropdown`}>
          {loading && results.length === 0 && (
            <div className="dest-row dest-loading"><Loader2 size={14} className="spin"/> Searching…</div>
          )}
          {results.map((r) => {
            const Icon = typeIcon[r.type] || MapPin;
            return (
              <button
                key={r.id}
                type="button"
                className="dest-row"
                onMouseDown={(e) => { e.preventDefault(); pick(r); }}
                data-testid={`dest-option-${r.id}`}
              >
                <Icon size={15}/>
                <div>
                  <div className="dest-row-label">{r.label}</div>
                  <small>{[r.city, r.state, r.country].filter(Boolean).join(" · ")} · <span style={{textTransform:'capitalize'}}>{r.type}</span></small>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
