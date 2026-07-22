import { useState } from "react";
import TripForm from "../components/TripForm";
import ComplianceStatusCard from "../components/ComplianceStatusCard";
import RouteMap from "../components/RouteMap";
import TripSummary from "../components/TripSummary";
import DailyLogSheet from "../components/DailyLogSheet";
import EmptyState from "../components/EmptyState";
import ErrorState from "../components/ErrorState";
import ResultsSkeleton from "../components/ResultsSkeleton";
import ThemeToggle from "../components/ThemeToggle";
import { planTrip, ApiError, ERROR_KIND } from "../api";

// The results area is always in exactly one of these.
const STATUS = {
  IDLE: "idle",
  LOADING: "loading",
  ERROR: "error",
  READY: "ready",
};

export default function Home() {
  const [status, setStatus] = useState(STATUS.IDLE);
  const [trip, setTrip] = useState(null);
  const [error, setError] = useState(null);
  const [lastSubmission, setLastSubmission] = useState(null);

  async function planTripFor(form) {
    setStatus(STATUS.LOADING);
    setError(null);
    setLastSubmission(form);

    try {
      const result = await planTrip(form);
      setTrip(result);
      setStatus(STATUS.READY);
    } catch (err) {
      // Anything that isn't an ApiError is a bug in our own code rather than a
      // failure of the request, so don't dress it up as a server problem.
      setError(
        err instanceof ApiError
          ? err
          : new ApiError("The planner hit an unexpected problem.", { kind: ERROR_KIND.SERVER })
      );
      setStatus(STATUS.ERROR);
    }
  }

  function handleRetry() {
    if (lastSubmission) planTripFor(lastSubmission);
  }

  return (
    <div className="home-page">
      <header className="masthead">
        <div className="masthead__bar">
          <span className="masthead__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M4 17h4M16 17h4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
              <circle cx="10" cy="17" r="2.4" stroke="currentColor" strokeWidth="2" />
              <circle cx="18" cy="17" r="2.4" stroke="currentColor" strokeWidth="2" />
              <path d="M3 17V8h9v9M12 11h4l3 3.2V17" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="masthead__wordmark">RouteLogix</span>
          <ThemeToggle />
        </div>

        <h1>Every mile, already logged.</h1>
        <p>
          Plan a route, and RouteLogix applies the hours-of-service rules as it goes; breaks,
          resets and fuel stops placed for you, with a compliant FMCSA log sheet for every day
          of the trip.
        </p>
      </header>

      <TripForm onSubmit={planTripFor} loading={status === STATUS.LOADING} />

      {status === STATUS.IDLE && <EmptyState />}

      {status === STATUS.LOADING && <ResultsSkeleton />}

      {status === STATUS.ERROR && <ErrorState error={error} onRetry={handleRetry} />}

      {status === STATUS.READY && trip && (
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
