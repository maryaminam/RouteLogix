const MONEY_FORMATTER = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function getSegments(trip) {
  return (trip?.logs || []).flatMap((log) => (log.segments || []).map((segment) => ({
    ...segment,
    day_number: log.day_number,
    date: log.date,
  })));
}

function isPaddingOffDuty(segment) {
  return segment.status === "OFF_DUTY" && (segment.label || "").toLowerCase() === "off duty";
}

function isFuelStop(segment) {
  return (segment.label || "").toLowerCase().includes("fuel stop");
}

function isRestStop(segment) {
  const label = (segment.label || "").toLowerCase();
  return label.includes("reset") || label.includes("restart") || label.includes("break") || segment.status === "SLEEPER_BERTH";
}

export default function TripSummary({ trip }) {
  if (!trip) {
    return null;
  }

  const segments = getSegments(trip);
  const drivingDays = trip.logs?.length || 0;
  const fuelStopsCount = segments.filter(isFuelStop).length;
  const restStopsCount = segments.filter(isRestStop).filter((segment) => !isPaddingOffDuty(segment)).length;
  const totalTripDurationHours = segments
    .filter((segment) => !isPaddingOffDuty(segment))
    .reduce((total, segment) => total + Number(segment.hours || 0), 0);

  const cards = [
    { label: "Total Distance", value: `${MONEY_FORMATTER.format(Number(trip.distance_miles || 0))} mi` },
    { label: "Estimated Driving Time", value: `${MONEY_FORMATTER.format(Number(trip.duration_hours || 0))} hrs` },
    { label: "Total Trip Duration", value: `${MONEY_FORMATTER.format(totalTripDurationHours)} hrs` },
    { label: "Number of Driving Days", value: String(drivingDays) },
    { label: "Fuel Stops", value: String(fuelStopsCount) },
    { label: "Rest Stops", value: String(restStopsCount) },
    { label: "Pickup Location", value: trip.pickup_location },
    { label: "Dropoff Location", value: trip.dropoff_location },
  ];

  return (
    <section className="trip-summary-card" aria-label="Trip overview">
      <div className="trip-summary-card__header">
        <div>
          <p className="trip-summary-card__eyebrow">Route Metrics</p>
          <h2>Trip Overview</h2>
        </div>
      </div>

      <div className="trip-summary-card__grid trip-summary-card__grid--compact">
        {cards.map((card) => (
          <div className="trip-summary-card__item" key={card.label}>
            <span>{card.label}</span>
            <strong>{card.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}