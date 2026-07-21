import { useState } from "react";
import TripForm from "../components/TripForm";
import RouteMap from "../components/RouteMap";
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
        <div className="results">
          {trip.cycle_summary && (
            <section className="cycle-summary-panel">
              <h2>Cycle check</h2>
              <div className="cycle-summary-grid">
                <div>
                  <span>Remaining cycle</span>
                  <strong>{trip.cycle_summary.remaining_cycle_hours_before_trip}h before / {trip.cycle_summary.remaining_cycle_hours_after_trip}h after</strong>
                </div>
                <div>
                  <span>Cycle after trip</span>
                  <strong>{trip.cycle_summary.cycle_after_trip_hours}h</strong>
                </div>
                <div>
                  <span>Restart</span>
                  <strong>{trip.cycle_summary.restart_required ? "Required" : "Not required"}</strong>
                </div>
                <div>
                  <span>Reset status</span>
                  <strong>{trip.cycle_summary.reset_status === "SLEEPER_BERTH" ? "Sleeper Berth" : trip.cycle_summary.reset_status}</strong>
                </div>
              </div>
            </section>
          )}
          <div className="map-panel">
            <RouteMap geometry={trip.route_geometry} stops={trip.stops} />
          </div>
          <div className="logs-panel">
            {trip.logs.map((log) => (
              <DailyLogSheet key={log.day_number} log={log} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
