import { useState } from "react";
import { Clock3, MapPin, Star, Plane, Hotel, BusFront, Car, ArrowRight } from "lucide-react";
import { money, clockTime, plural } from "../lib/format";

const typeIcon = { flight: Plane, hotel: Hotel, bus: BusFront, cab: Car };

export default function ResultCard({ item, onOpen }) {
  const Icon = typeIcon[item.type] || Plane;
  const [imgFailed, setImgFailed] = useState(false);
  const isLive = item.mode === "LIVE";
  const dep = clockTime(item.departure);
  const arr = clockTime(item.arrival);
  const nights = Number(item.nights) || 0;
  const rating = Number(item.rating) || 0;
  const stops = item.stops;
  return (
    <article className="result-card" onClick={() => onOpen(item)} data-testid={`result-card-${item.id}`}>
      <div className="result-media">
        {item.image && !imgFailed
          ? <img src={item.image} alt={item.title} loading="lazy" onError={() => setImgFailed(true)}/>
          : <div style={{display:'grid',placeItems:'center',height:'100%',color:'var(--teal)'}}><Icon size={48}/></div>}
      </div>
      <div className="result-body">
        <span className="result-type"><Icon size={11}/> {item.type}{!isLive && <em className="demo-chip" data-testid="demo-chip">Demo</em>}</span>
        <h3 data-testid={`result-title-${item.id}`}>{item.title}</h3>
        <div className="result-sub">{item.brand}</div>
        <div className="result-meta">
          {item.duration && <span><Clock3 size={13}/> {item.duration}</span>}
          {rating > 0 && <span><Star size={13} style={{color:'var(--gold)',fill:'var(--gold)'}}/> {rating}</span>}
          {item.location && <span><MapPin size={13}/> {item.location}</span>}
          {stops !== undefined && stops !== null && <span>{stops === 0 ? "Non-stop" : plural(Number(stops), "stop")}</span>}
          {dep && <span>{dep}{arr ? ` - ${arr}` : ""}{arr && arr < dep ? " (+1)" : ""}</span>}
        </div>
        <div className="result-tags">{(item.meta || []).slice(0,3).map(t => <span key={t}>{t}</span>)}</div>
      </div>
      <div className="result-price-col">
        <div>
          <small>{isLive ? "Live price" : "Sample price"}</small>
          <strong>{money(item.price)}</strong>
          {item.type === "hotel" && nights > 0 ? <small>{plural(nights, "night")} total</small> : null}
        </div>
        <button className="result-cta" data-testid={`book-btn-${item.id}`} onClick={(e) => { e.stopPropagation(); onOpen(item); }}>
          View <ArrowRight size={14}/>
        </button>
      </div>
    </article>
  );
}
