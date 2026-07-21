const NUMBER_FORMATTER = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

function formatResetType(resetType) {
  if (!resetType) {
    return "N/A";
  }

  return resetType
    .toString()
    .toLowerCase()
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function formatHours(value) {
  return `${NUMBER_FORMATTER.format(Number(value || 0))} hrs`;
}

export default function ComplianceStatusCard({ trip }) {
  const summary = trip?.cycle_summary || {};
  const restartRequired = Boolean(summary.restart_required);
  const statusLabel = restartRequired ? "Restart Required" : "HOS Compliant";
  const description = restartRequired
    ? "Trip exceeds available cycle hours"
    : "No violations detected";
  const statusClassName = restartRequired ? "hos-status-card--warning" : "hos-status-card--good";

  const metrics = [
    { label: "Current Cycle Used", value: formatHours(summary.current_cycle_used_hours ?? trip?.current_cycle_used_hours) },
    { label: "Remaining Cycle Before Trip", value: formatHours(summary.remaining_cycle_hours_before_trip) },
    { label: "Remaining Cycle After Trip", value: formatHours(summary.remaining_cycle_hours_after_trip) },
    { label: "Restart Required", value: restartRequired ? "Yes" : "No" },
    { label: "Reset Type", value: formatResetType(summary.reset_status) },
  ];

  return (
    <section className={`hos-status-card ${statusClassName}`} aria-label="Hours of service summary" aria-live="polite">
      <div className="hos-status-card__header">
        <div>
          <p className="hos-status-card__eyebrow">Hours of Service Summary</p>
          <h2>{statusLabel}</h2>
          <p className="hos-status-card__description">{description}</p>
        </div>
        <div className="hos-status-card__badge" aria-hidden="true">
          {restartRequired ? "!" : "✓"}
        </div>
      </div>

      <div className="hos-status-card__grid">
        {metrics.map((metric) => (
          <div className="hos-status-card__metric" key={metric.label}>
            <span>{metric.label}</span>
            <strong>{metric.value}</strong>
          </div>
        ))}
      </div>
    </section>
  );
}