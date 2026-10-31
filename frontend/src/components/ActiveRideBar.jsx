import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ChevronRight, Zap } from "lucide-react";
import { useAuth } from "../lib/auth";
import { rideApi } from "../lib/rides";

// A thin bar under the menu while a ride is going on, so the rider can get back to it from any page.
export default function ActiveRideBar() {
  const { user } = useAuth();
  const { pathname } = useLocation();
  const [ride, setRide] = useState(null);
  const onRide = /^\/ride\//.test(pathname);

  useEffect(() => {
    if (!user) { setRide(null); return undefined; }
    let live = true;
    let timer = null;
    const tick = async () => {
      try { const r = await rideApi.active(); if (live) setRide(r); } catch { /* the bar is a convenience */ }
      if (live) timer = setTimeout(tick, document.hidden ? 60000 : 12000);
    };
    tick();
    return () => { live = false; clearTimeout(timer); };
  }, [user, pathname]);

  if (!user || !ride || onRide) return null;
  return (
    <Link to={`/ride/${ride.ride_id}`} className="active-ride-bar" data-testid="active-ride-bar">
      <Zap size={15} />
      <span><b>{ride.state.stage === "scheduled" ? "Ride scheduled" : "Ride in progress"}</b> · {ride.state.headline}</span>
      <span className="active-ride-go">Track <ChevronRight size={14} /></span>
    </Link>
  );
}
