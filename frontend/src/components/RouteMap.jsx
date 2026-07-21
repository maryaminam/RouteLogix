import { MapContainer, TileLayer, Marker, Polyline, Popup } from "react-leaflet";
import "leaflet/dist/leaflet.css";

// Placeholder — will be fleshed out with proper marker icons and stop popups.
export default function RouteMap({ geometry = [], stops = [] }) {
  if (!geometry.length) {
    return <div className="map-placeholder">Route will appear here after planning a trip.</div>;
  }

  const center = geometry[Math.floor(geometry.length / 2)];

  return (
    <MapContainer center={center} zoom={6} style={{ height: "100%", width: "100%" }}>
      <TileLayer
        attribution='&copy; OpenStreetMap contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <Polyline positions={geometry} />
      {stops.map((stop, i) => (
        <Marker key={i} position={[stop.lat, stop.lng]}>
          <Popup>{stop.type}</Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
