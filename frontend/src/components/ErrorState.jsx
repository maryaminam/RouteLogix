import { ERROR_KIND } from "../api";

// One entry per failure path the API can produce. `detail` is the backend's own
// message, shown underneath as supporting evidence rather than as the headline.
const PRESENTATION = {
  [ERROR_KIND.VALIDATION]: {
    icon: "✍️",
    title: "Check the trip details",
    guidance: "The planner rejected these values before routing anything.",
  },
  [ERROR_KIND.GEOCODING]: {
    icon: "📍",
    title: "We couldn't find one of those locations",
    guidance:
      "Try a city and state, like \"Denver, CO\". The lookup also throttles heavily under load, so a retry in a few seconds often works.",
  },
  [ERROR_KIND.ROUTING]: {
    icon: "🛣️",
    title: "No drivable route between those stops",
    guidance:
      "The locations resolved, but the routing service couldn't connect them. That usually means the stops are on separate road networks, or the service is temporarily down.",
  },
  [ERROR_KIND.NETWORK]: {
    icon: "🔌",
    title: "Can't reach the planning service",
    guidance:
      "The request never left the browser. Check your connection, and confirm the backend is running.",
  },
  [ERROR_KIND.SERVER]: {
    icon: "⚠️",
    title: "Something broke on our end",
    guidance: "The request reached the server but it couldn't complete. Try again in a moment.",
  },
};

const FIELD_LABELS = {
  current_location: "Current location",
  pickup_location: "Pickup location",
  dropoff_location: "Dropoff location",
  current_cycle_used_hours: "Current cycle used (hrs)",
};

export default function ErrorState({ error, onRetry }) {
  if (!error) return null;

  const { icon, title, guidance } = PRESENTATION[error.kind] || PRESENTATION[ERROR_KIND.SERVER];
  const fieldErrors = error.fieldErrors ? Object.entries(error.fieldErrors) : [];

  return (
    <section className="state-card state-card--error" role="alert">
      <span className="state-card__icon" aria-hidden="true">
        {icon}
      </span>
      <h2 className="state-card__title">{title}</h2>
      <p className="state-card__message">{guidance}</p>

      {fieldErrors.length > 0 ? (
        <ul className="state-card__list state-card__list--fields">
          {fieldErrors.map(([field, message]) => (
            <li key={field}>
              <strong>{FIELD_LABELS[field] || field}:</strong> {message}
            </li>
          ))}
        </ul>
      ) : (
        error.message && <p className="state-card__detail">{error.message}</p>
      )}

      {onRetry && (
        <button type="button" className="state-card__retry" onClick={onRetry}>
          Try again
        </button>
      )}
    </section>
  );
}
