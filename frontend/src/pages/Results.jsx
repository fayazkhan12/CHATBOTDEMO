import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import SearchBar from "../components/SearchBar";
import ResultCard from "../components/ResultCard";
import { http } from "../lib/api";
import { money, shortDate, dateRange, plural, dayFromNow } from "../lib/format";

const NOUN = { hotels: ["hotel", "hotels"], flights: ["flight", "flights"], buses: ["bus", "buses"], cabs: ["cab", "cabs"] };

function searchError(e) {
  const status = e && e.response && e.response.status;
  if (status === 429) return "Too many searches in a short time. Please wait a minute and try again.";
  return "Search is temporarily unavailable. Try again.";
}

export default function Results() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const initial = useMemo(() => Object.fromEntries(params.entries()), [params]);
  const service = initial.service || "flights";
  // a link without dates (the Discover menu, say) searches for tomorrow, which is also what the form on this page shows
  const fallback = useMemo(() => ({ start: dayFromNow(1), end: dayFromNow(3) }), []);
  const startDate = initial.start_date || fallback.start;
  const endDate = initial.end_date || fallback.end;
  const [data, setData] = useState({ results: [], mode: "DEMO", service });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [sort, setSort] = useState("recommended");
  const [cap, setCap] = useState(null); // the highest price the visitor allows; null = no limit

  // what we ask the server. Sorting happens here in the browser, so changing it never searches again.
  const body = useMemo(() => {
    const out = {
      service,
      origin: initial.origin || "New Delhi",
      destination: initial.destination || "Goa",
      start_date: startDate,
      end_date: endDate,
      travellers: Number(initial.travellers || 2),
    };
    if (initial.destination_id) out.destination_id = initial.destination_id;
    return out;
  }, [initial, service, startDate, endDate]);

  useEffect(() => {
    let stale = false;
    setLoading(true);
    setError("");
    setCap(null);
    http.post("/travel/search", body)
      .then(({ data: res }) => {
        if (stale) return;
        setData(res);
        // cache so the detail page can look up items
        http.post("/travel/cache", res.results).catch(() => {});
      })
      .catch((e) => { if (!stale) setError(searchError(e)); })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [body, attempt]);

  const showMore = async () => {
    if (loadingMore) return;
    setLoadingMore(true);
    setError("");
    try {
      const { data: res } = await http.post("/travel/search", { ...body, page: (Number(data.page) || 1) + 1 });
      http.post("/travel/cache", res.results).catch(() => {});
      setData((old) => {
        const seen = new Set(old.results.map((r) => r.id));
        const fresh = res.results.filter((r) => !seen.has(r.id));
        return {
          ...old,
          results: [...old.results, ...fresh],
          page: res.page || (Number(old.page) || 1) + 1,
          total: res.total === null || res.total === undefined ? old.total : res.total,
          has_more: !!res.has_more && fresh.length > 0,
        };
      });
    } catch (e) {
      setError(searchError(e));
    } finally {
      setLoadingMore(false);
    }
  };

  const open = (item) => {
    const svc = data.service || "hotels";
    navigate(`/detail/${svc}/${encodeURIComponent(item.id)}`);
  };

  const prices = data.results.map((r) => Number(r.price) || 0).filter((p) => p > 0);
  const lo = prices.length ? Math.floor(Math.min(...prices) / 100) * 100 : 0;
  const hi = prices.length ? Math.ceil(Math.max(...prices) / 100) * 100 : 0;
  const sliderValue = cap === null ? hi : Math.min(Math.max(cap, lo), hi);

  const filtered = useMemo(() => {
    let out = [...data.results];
    if (cap !== null) out = out.filter((r) => r.price <= cap);
    if (sort === "price") out.sort((a, b) => a.price - b.price);
    else if (sort === "rating") out.sort((a, b) => (b.rating || 0) - (a.rating || 0));
    return out;
  }, [data.results, cap, sort]);

  const noun = NOUN[data.service] || [data.service, data.service];
  const total = Number(data.total) || 0;
  const isLive = data.mode === "LIVE" || service === "hotels";
  const heading = loading
    ? "Searching…"
    : total > data.results.length
      ? `Showing ${filtered.length} of ${total} ${noun[1]}`
      : `${filtered.length} ${filtered.length === 1 ? noun[0] : noun[1]} available`;

  // what was really searched (the server fixes dates in the past), falling back to what was asked
  const first = data.results[0] || {};
  const subtitle = (() => {
    if (service === "hotels") {
      const parts = [`Hotels in ${initial.destination || "your city"}`];
      const range = dateRange(first.check_in || startDate, first.check_out || endDate);
      if (range) parts.push(range);
      const guests = Number(first.guests || initial.travellers);
      if (guests > 0) parts.push(plural(guests, "guest"));
      return parts.join(" · ");
    }
    const parts = [`${initial.origin || "New Delhi"} → ${initial.destination || "Goa"}`];
    const day = shortDate(first.check_in || startDate);
    if (day) parts.push(day);
    return parts.join(" · ");
  })();

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
              type="range" min={lo} max={hi} step={100} value={sliderValue} disabled={hi <= lo}
              onChange={(e) => { const v = Number(e.target.value); setCap(v >= hi ? null : v); }}
              data-testid="filter-price-range"
            />
            <div style={{color:'var(--muted)',fontSize:12,marginTop:6}}>{hi > 0 ? `Up to ${money(sliderValue)}` : "No prices yet"}</div>
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
            <div className="filter-label">Data source</div>
            <span className={isLive ? "badge-live" : "badge-demo"} data-testid="data-badge">{isLive ? "Live prices" : "Demo data"}</span>
            <p style={{color:'var(--muted)',fontSize:11,marginTop:10,lineHeight:1.5}} data-testid="data-note">
              {isLive
                ? "Prices come live from our hotel partners and can change."
                : "Sample listings that show how search and booking work. No real tickets are issued."}
            </p>
          </div>
        </aside>

        <main className="results-main">
          <div className="results-head">
            <div>
              <h2 data-testid="results-heading">{heading}</h2>
              <p data-testid="results-subtitle">{subtitle}</p>
            </div>
            <div style={{display:'flex',gap:12,alignItems:'center'}}>
              <select className="sort-select" value={sort} onChange={(e)=>setSort(e.target.value)} data-testid="sort-select">
                <option value="recommended">Recommended</option>
                <option value="price">Lowest price</option>
                <option value="rating">Top rated</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="error-banner" data-testid="error-banner" role="alert">
              {error}{" "}
              <button className="btn-ghost" style={{padding:'4px 12px',marginLeft:8}} onClick={() => setAttempt((n) => n + 1)} data-testid="retry-btn">Try again</button>
            </div>
          )}
          {loading ? (
            <div className="empty-state" data-testid="results-loading">
              <span className="spinner"/> Finding best options&hellip;
              {service === "hotels" && <div style={{marginTop:8,fontSize:12}}>Checking live hotel prices. This can take up to 30 seconds.</div>}
            </div>
          ) : data.results.length === 0 ? (
            !error && (
              <div className="empty-state" data-testid="results-empty">
                {data.note || `No ${noun[1]} found for these dates and place. Try other dates or another destination.`}
              </div>
            )
          ) : filtered.length === 0 ? (
            <div className="empty-state" data-testid="results-filtered-out">
              No results match your filters. Try widening the price range.
              <div><button className="btn-ghost" style={{marginTop:12}} onClick={() => setCap(null)} data-testid="clear-filter-btn">Clear price filter</button></div>
            </div>
          ) : (
            <div className="result-row">
              {filtered.map(item => <ResultCard key={item.id} item={item} onOpen={open}/>)}
            </div>
          )}

          {!loading && data.has_more && data.results.length > 0 && (
            <div className="show-more-row">
              <button className="btn-ghost" onClick={showMore} disabled={loadingMore} data-testid="show-more-btn">
                {loadingMore ? "Loading more…" : `Show more ${noun[1]}`}
              </button>
              {loadingMore && service === "hotels" && <small>Checking live hotel prices. This can take up to 30 seconds.</small>}
            </div>
          )}
        </main>
      </div>
    </>
  );
}
