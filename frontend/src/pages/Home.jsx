import { useState } from "react";
import TripForm from "../components/TripForm";
import ComplianceStatusCard from "../components/ComplianceStatusCard";
import RouteMap from "../components/RouteMap";
import TripSummary from "../components/TripSummary";
import DailyLogSheet from "../components/DailyLogSheet";
import { planTrip, ApiError } from "../api";

export default function Home() {
  const [trip, setTrip] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  async function handleSubmit(form) {
    setLoading(true);
    setError(null);
    try {
      const result = await planTrip(form);
      setTrip(result);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="home-page">
      <header>
        <h1>ELD Trip Planner</h1>
        <p>Plan a route and auto-generate compliant daily log sheets.</p>
      </header>

      <TripForm onSubmit={handleSubmit} loading={loading} />

      {error && <p className="error">{error}</p>}

      {trip && (
        <div className="results results--dashboard">
          <ComplianceStatusCard trip={trip} />
          <RouteMap trip={trip} geometry={trip.route_geometry} stops={trip.stops} />
          <TripSummary trip={trip} />
          <div className="logs-panel">
            <DailyLogSheet logs={trip.logs} />
          </div>
        </div>
      )}
    </div>
  );
}
