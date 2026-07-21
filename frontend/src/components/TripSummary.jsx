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
  const fuelStopsCount = segments.filter(isFuelStop).length;
  const restStopsCount = segments.filter(isRestStop).filter((segment) => !isPaddingOffDuty(segment)).length;
  const totalTripDurationHours = segments
    .filter((segment) => !isPaddingOffDuty(segment))
    .reduce((total, segment) => total + Number(segment.hours || 0), 0);

  const summary = trip.cycle_summary || {};
  const currentCycleUsed = summary.current_cycle_used_hours ?? trip.current_cycle_used_hours ?? 0;
  const cycleAfterTrip = summary.cycle_after_trip_hours ?? null;
  const cards = [
    { label: "Total Distance", value: `${MONEY_FORMATTER.format(Number(trip.distance_miles || 0))} mi` },
    { label: "Estimated Driving Time", value: `${MONEY_FORMATTER.format(Number(trip.duration_hours || 0))} hrs` },
    { label: "Total Trip Duration", value: `${MONEY_FORMATTER.format(totalTripDurationHours)} hrs` },
    { label: "Fuel Stops Count", value: String(fuelStopsCount) },
    { label: "Rest Stops Count", value: String(restStopsCount) },
    { label: "Pickup Location", value: trip.pickup_location },
    { label: "Dropoff Location", value: trip.dropoff_location },
    { label: "Current Cycle Used", value: `${MONEY_FORMATTER.format(Number(currentCycleUsed))} hrs` },
    { label: "Cycle Remaining After Trip", value: `${MONEY_FORMATTER.format(Number(summary.remaining_cycle_hours_after_trip ?? 0))} hrs` },
  ];

  return (
    <section className="trip-summary-card" aria-label="Trip summary">
      <div className="trip-summary-card__header">
        <div>
          <p className="trip-summary-card__eyebrow">Trip Overview</p>
        </div>
        <div className="trip-summary-card__status">
          <span>Cycle after trip</span>
          <strong>{cycleAfterTrip != null ? `${MONEY_FORMATTER.format(Number(cycleAfterTrip))} hrs` : "N/A"}</strong>
        </div>
      </div>

      <div className="trip-summary-card__grid">
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