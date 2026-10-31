import { lazy, Suspense, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Loader2, ShieldCheck } from "lucide-react";
import VehicleIcon from "../components/VehicleIcon";
import { rideApi } from "../lib/rides";

const RideMap = lazy(() => import("../components/RideMap"));

// What a friend sees from the link a rider shared: where the ride is and who is driving. No login, no personal details.
export default function RideShare() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [gone, setGone] = useState(false);

  useEffect(() => {
    let live = true;
    let timer = null;
    const tick = async () => {
      try {
        const r = await rideApi.shared(token);
        if (!live) return;
        setData(r);
        if (r.state.final) return;
      } catch (e) {
        if (!live) return;
        if (e && e.response && e.response.status === 404) { setGone(true); return; }
      }
      timer = setTimeout(tick, document.hidden ? 10000 : 3000);
    };
    tick();
    return () => { live = false; clearTimeout(timer); };
  }, [token]);

  if (gone) return <div className="empty-state" data-testid="share-gone"><h2>This ride link is not available any more</h2><Link className="btn-primary" to="/">DestinoWay home</Link></div>;
  if (!data) return <div className="ride-loading" role="status"><Loader2 className="spin" size={22} /> Loading ride...</div>;
  const st = data.state;
  const live = !st.final;
  return (
    <div className="ride-track" data-testid="share-page" data-stage={st.stage}>
      <section className="ride-track-map">
        <Suspense fallback={<div className="ride-map ride-map-loading"><Loader2 className="spin" size={20} /></div>}>
          <RideMap pickup={data.pickup} drop={data.drop} route={data.route} vehicle={live ? st.vehicle_pos : null} vehicleKind={data.vehicle.key} follow label="Shared ride map" />
        </Suspense>
      </section>
      <section className="ride-sheet" aria-live="polite">
        <div className="ride-head">
          <VehicleIcon kind={data.vehicle.key} size={26} />
          <div><h1>Following a DestinoWay ride</h1><p data-testid="share-headline">{st.headline}</p></div>
          {st.eta_min != null && live && <span className="ride-eta"><b>{st.eta_min}</b> min</span>}
        </div>
        {data.captain && (
          <div className="ride-captain">
            <span className="ride-captain-info"><b>{data.captain.first_name}</b><small>{data.captain.vehicle_color} {data.captain.vehicle_model}</small></span>
            <span className="ride-plate">{data.captain.plate}</span>
          </div>
        )}
        <ol className="ride-route-list">
          <li><span className="dot pickup" /><span><small>From</small><b>{data.pickup.name}</b></span></li>
          <li><span className="dot drop" /><span><small>To</small><b>{data.drop.name}</b></span></li>
        </ol>
        <p className="ride-demo"><ShieldCheck size={13} /> {data.demo_note}</p>
      </section>
    </div>
  );
}
