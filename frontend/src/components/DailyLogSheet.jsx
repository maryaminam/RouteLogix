// Placeholder — will be replaced with a full SVG FMCSA-style grid renderer.
export default function DailyLogSheet({ log }) {
  return (
    <div className="log-sheet-placeholder">
      <h3>Day {log.day_number} — {log.date}</h3>
      <p>Driving: {log.total_driving_hours}h | On duty: {log.total_on_duty_hours}h | Off duty: {log.total_off_duty_hours}h | Sleeper: {log.total_sleeper_berth_hours}h</p>
      <pre>{JSON.stringify(log.segments, null, 2)}</pre>
    </div>
  );
}
