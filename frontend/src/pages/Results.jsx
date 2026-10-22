import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import SearchBar from "../components/SearchBar";
import ResultCard from "../components/ResultCard";
import { http } from "../lib/api";

export default function Results() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initial = useMemo(() => Object.fromEntries(params.entries()), [params]);
  const [data, setData] = useState({ results: [], mode: "DEMO", service: initial.service || "flights" });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sort, setSort] = useState("recommended");
  const [maxPrice, setMaxPrice] = useState(0);

  const fetchResults = useCallback(async (payload) => {
    setLoading(true); setError("");
    try {
      const { data: res } = await http.post("/travel/search", {
        ...payload,
        travellers: Number(payload.travellers || 2),
        sort,
      });
      setData(res);
      // cache so detail page can look up items
      http.post("/travel/cache", res.results).catch(() => {});
      if (res.results.length) {
        const prices = res.results.map(r => r.price);
        setMaxPrice(Math.ceil(Math.max(...prices) * 1.05));
      }
    } catch (e) {
      setError("Search is temporarily unavailable. Try again.");
    } finally {
      setLoading(false);
    }
  }, [sort]);

  useEffect(() => {
    const payload = {
      service: initial.service || "flights",
      origin: initial.origin || "New Delhi",
      destination: initial.destination || "Goa",
      start_date: initial.start_date,
      end_date: initial.end_date,
      travellers: Number(initial.travellers || 2),
    };
    fetchResults(payload);
  }, [initial, fetchResults]);

  const open = (item) => {
    const service = data.service || "hotels";
    navigate(`/detail/${service}/${encodeURIComponent(item.id)}`);
  };

  const filtered = useMemo(() => {
    let out = [...data.results];
    if (maxPrice) out = out.filter(r => r.price <= maxPrice);
    if (sort === "price") out.sort((a,b) => a.price - b.price);
    else if (sort === "rating") out.sort((a,b) => (b.rating||0) - (a.rating||0));
    return out;
  }, [data.results, maxPrice, sort]);

  return (
    <>
      <div className="search-card" style={{marginTop: 32}}>
        <SearchBar initial={initial} onSubmit={(p) => {
          const q = new URLSearchParams(p).toString();
          navigate(`/search?${q}`);
        }}/>
      </div>
      <div className="results-page" data-testid="results-page">
        <aside className="filter-panel">
          <h3>Refine</h3>
          <div className="filter-group">
            <div className="filter-label">Max price</div>
            <input
              type="range" min={1000} max={maxPrice || 50000} value={maxPrice}
              onChange={(e) => setMaxPrice(Number(e.target.value))}
              data-testid="filter-price-range"
            />
            <div style={{color:'var(--muted)',fontSize:12,marginTop:6}}>Up to ₹{Number(maxPrice).toLocaleString("en-IN")}</div>
          </div>
          <div className="filter-group">
            <div className="filter-label">Sort by</div>
            <div className="filter-chip-row">
              {[{id:"recommended",l:"Recommended"},{id:"price",l:"Lowest price"},{id:"rating",l:"Top rated"}].map(c => (
                <button key={c.id} className={sort === c.id ? "filter-chip active" : "filter-chip"} onClick={() => setSort(c.id)} data-testid={`sort-${c.id}`}>{c.l}</button>
              ))}
            </div>
          </div>
          <div className="filter-group">
            <div className="filter-label">Service mode</div>
            <span className={data.mode === "LIVE" ? "badge-live" : "badge-demo"}>{data.mode === "LIVE" ? "Live inventory" : "Demo inventory"}</span>
            {data.mode !== "LIVE" && <p style={{color:'var(--muted)',fontSize:11,marginTop:10,lineHeight:1.5}}>Add Akbar / Travelportal credentials in backend <code>.env</code> to switch to live.</p>}
          </div>
        </aside>

        <main className="results-main">
          <div className="results-head">
            <div>
              <h2 data-testid="results-heading">{loading ? "Searching…" : `${filtered.length} ${data.service} available`}</h2>
              <p>{initial.origin} → {initial.destination} · {initial.start_date} to {initial.end_date}</p>
            </div>
            <div style={{display:'flex',gap:12,alignItems:'center'}}>
              <select className="sort-select" value={sort} onChange={(e)=>setSort(e.target.value)} data-testid="sort-select">
                <option value="recommended">Recommended</option>
                <option value="price">Lowest price</option>
                <option value="rating">Top rated</option>
              </select>
            </div>
          </div>

          {error && <div className="error-banner" data-testid="error-banner">{error}</div>}
          {loading ? (
            <div className="empty-state"><span className="spinner"/> Finding best options…</div>
          ) : filtered.length === 0 ? (
            <div className="empty-state">No results match your filters. Try widening the price range.</div>
          ) : (
            <div className="result-row">
              {filtered.map(item => <ResultCard key={item.id} item={item} onOpen={open}/>)}
            </div>
          )}
        </main>
      </div>
    </>
  );
}
