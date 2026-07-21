export default function EmptyState() {
  return (
    <section className="state-card state-card--empty" aria-live="polite">
      <span className="state-card__icon" aria-hidden="true">
        🗺️
      </span>
      <h2 className="state-card__title">No trip planned yet</h2>
      <p className="state-card__message">
        Enter the driver&apos;s current location, the pickup and the dropoff, plus the hours
        already used in their 70-hour cycle. We&apos;ll route the trip, apply the HOS rules and
        generate the daily log sheets.
      </p>
      <ul className="state-card__list">
        <li>Use a city and state, like &quot;Denver, CO&quot;, for the most reliable match.</li>
        <li>Rest breaks, fuel stops and 34-hour restarts are inserted automatically.</li>
      </ul>
    </section>
  );
}
