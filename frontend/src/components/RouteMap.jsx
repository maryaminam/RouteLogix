import { useEffect } from "react";
import { MapContainer, TileLayer, Marker, Polyline, Popup, useMap } from "react-leaflet";
import { divIcon } from "leaflet";
import "leaflet/dist/leaflet.css";

function getSegments(trip) {
  return (trip?.logs || []).flatMap((log) => log.segments || []);
}

function isFuelStop(segment) {
  return (segment.label || "").toLowerCase().includes("fuel stop");
}

function isRestStop(segment) {
  const label = (segment.label || "").toLowerCase();
  return label.includes("reset") || label.includes("restart") || label.includes("break") || segment.status === "SLEEPER_BERTH";
}

function countStops(trip) {
  const segments = getSegments(trip);
  const fuelStops = segments.filter(isFuelStop).length;
  const restStops = segments.filter(isRestStop).filter((segment) => (segment.label || "").toLowerCase() !== "off duty").length;
  return { fuelStops, restStops };
}

function getPoint(geometry, ratio) {
  if (!geometry.length) {
    return null;
  }

  if (geometry.length === 1) {
    return geometry[0];
  }

  const points = geometry.map(([latitude, longitude]) => ({ latitude, longitude }));
  const distances = [0];
  let totalDistance = 0;

  for (let index = 1; index < points.length; index += 1) {
    const left = points[index - 1];
    const right = points[index];
    const segmentDistance = Math.hypot(right.latitude - left.latitude, right.longitude - left.longitude);
    totalDistance += segmentDistance;
    distances.push(totalDistance);
  }

  const targetDistance = totalDistance * ratio;

  for (let index = 1; index < distances.length; index += 1) {
    if (distances[index] >= targetDistance) {
      const left = points[index - 1];
      const right = points[index];
      const segmentDistance = distances[index] - distances[index - 1] || 1;
      const localRatio = (targetDistance - distances[index - 1]) / segmentDistance;
      return [
        left.latitude + (right.latitude - left.latitude) * localRatio,
        left.longitude + (right.longitude - left.longitude) * localRatio,
      ];
    }
  }

  return geometry[geometry.length - 1];
}

function createMarkerIcon(kind, label) {
  return divIcon({
    className: `route-marker route-marker--${kind}`,
    html: `<span>${label}</span>`,
    iconSize: [52, 52],
    iconAnchor: [26, 48],
    popupAnchor: [0, -40],
  });
}

function getSyntheticStops(geometry, count, kind, labelPrefix, startRatio, endRatio) {
  if (!count || !geometry.length) {
    return [];
  }

  if (count === 1) {
    return [{ kind, label: `${labelPrefix} 1`, position: getPoint(geometry, 0.5) }];
  }

  return Array.from({ length: count }, (_, index) => {
    const ratio = startRatio + ((endRatio - startRatio) * index) / (count - 1);
    return {
      kind,
      label: `${labelPrefix} ${index + 1}`,
      position: getPoint(geometry, ratio),
    };
  });
}

function buildMarkerStops(trip, geometry, stops) {
  const structuredStops = stops.map((stop) => ({
    kind: stop.type,
    label:
      stop.type === "current"
        ? "Current Location"
        : stop.type === "pickup"
          ? "Pickup"
          : stop.type === "dropoff"
            ? "Dropoff"
            : stop.type,
    position: [stop.lat, stop.lng],
  }));

  const { fuelStops, restStops } = countStops(trip);
  const syntheticStops = [
    ...getSyntheticStops(geometry, fuelStops, "fuel", "Fuel Stop", 0.2, 0.8),
    ...getSyntheticStops(geometry, restStops, "rest", "Rest Stop", 0.3, 0.7),
  ].filter((stop) => stop.position);

  return [...structuredStops, ...syntheticStops];
}

function MapResizeFix() {
  const map = useMap();

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      map.invalidateSize();
    });

    return () => window.cancelAnimationFrame(frame);
  }, [map]);

  return null;
}

export default function RouteMap({ trip, geometry = [], stops = [] }) {
  const routeGeometry = geometry.length ? geometry : trip?.route_geometry || [];

  if (!routeGeometry.length) {
    return <div className="map-placeholder">Route will appear here after planning a trip.</div>;
  }

  const center = routeGeometry[Math.floor(routeGeometry.length / 2)];
  const mapStops = buildMarkerStops(trip, routeGeometry, stops);
  const { fuelStops, restStops } = countStops(trip);

  return (
    <section className="route-map-card" aria-label="Route map and summary">
      <div className="map-panel route-map-card__map">
        <MapContainer center={center} zoom={6} style={{ height: "100%", width: "100%" }} aria-label="Trip route map">
          <MapResizeFix />
          <TileLayer
            attribution='&copy; OpenStreetMap contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Polyline positions={routeGeometry} />
          {mapStops.map((stop, index) => (
            <Marker
              key={`${stop.kind}-${index}`}
              position={stop.position}
              icon={createMarkerIcon(stop.kind, stop.kind === "current" ? "C" : stop.kind === "pickup" ? "P" : stop.kind === "dropoff" ? "D" : stop.kind === "fuel" ? "F" : "R")}
            >
              <Popup>{stop.label}</Popup>
            </Marker>
          ))}
        </MapContainer>
      </div>
    </section>
  );
}
