import { vehicleSvg } from "../lib/rideicons";

// kind: bike | auto | mini | sedan | suv (anything else draws a cab)
export default function VehicleIcon({ kind, size = 24, className = "" }) {
  return <span className={`vehicle-icon ${className}`} aria-hidden="true" dangerouslySetInnerHTML={{ __html: vehicleSvg(kind, size) }} />;
}
