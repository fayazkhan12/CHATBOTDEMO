import { Clock3, MapPin, Star, Plane, Hotel, BusFront, Car, ArrowRight } from "lucide-react";

const typeIcon = { flight: Plane, hotel: Hotel, bus: BusFront, cab: Car };

export default function ResultCard({ item, onOpen }) {
  const Icon = typeIcon[item.type] || Plane;
  return (
    <article className="result-card" onClick={() => onOpen(item)} data-testid={`result-card-${item.id}`}>
      <div className="result-media">
        {item.image ? <img src={item.image} alt={item.title}/> : <div style={{display:'grid',placeItems:'center',height:'100%',color:'var(--teal)'}}><Icon size={48}/></div>}
      </div>
      <div className="result-body">
        <span className="result-type"><Icon size={11}/> {item.type}</span>
        <h3 data-testid={`result-title-${item.id}`}>{item.title}</h3>
        <div className="result-sub">{item.brand}</div>
        <div className="result-meta">
          {item.duration && <span><Clock3 size={13}/> {item.duration}</span>}
          {item.rating !== undefined && <span><Star size={13} style={{color:'var(--gold)',fill:'var(--gold)'}}/> {item.rating}</span>}
          {item.location && <span><MapPin size={13}/> {item.location}</span>}
          {item.stops !== undefined && <span>{item.stops === 0 ? "Non-stop" : `${item.stops} stop`}</span>}
          {item.departure && <span>{new Date(item.departure).toTimeString().slice(0,5)}</span>}
        </div>
        <div className="result-tags">{(item.meta || []).slice(0,3).map(t => <span key={t}>{t}</span>)}</div>
      </div>
      <div className="result-price-col">
        <small>{item.mode === "LIVE" ? "Live price" : "From"}</small>
        <strong>₹{Number(item.price || 0).toLocaleString("en-IN")}</strong>
        <button className="result-cta" data-testid={`book-btn-${item.id}`} onClick={(e) => { e.stopPropagation(); onOpen(item); }}>
          View <ArrowRight size={14}/>
        </button>
      </div>
    </article>
  );
}
