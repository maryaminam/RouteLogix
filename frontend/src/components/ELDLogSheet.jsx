import { useRef } from "react";
import LogSheetPdfButton from "./LogSheetPdfButton";

/**
 * Duty statuses are a categorical scale — identity, not magnitude — so the
 * hues are assigned in a fixed validated order, never by rank.
 *
 * Checked with the dataviz palette validator against the #f5f5f7 grid surface:
 * chroma floor, lightness band, CVD separation (worst adjacent ΔE 9.2 deutan)
 * and normal-vision floor (16.3) all pass. The colours these replace put
 * Driving (#16a34a) and On Duty (#f97316) at ΔE 4.8 under protanopia — a
 * red-green colourblind driver could not tell them apart on their own log.
 * Two slots sit below 3:1 against the surface, so the relief rule applies:
 * every row is direct-labelled and every total is written out in text.
 */
const STATUS_ROWS = [
  { key: "OFF_DUTY", label: "Off Duty", total: "total_off_duty_hours", stroke: "#2a78d6" },
  { key: "SLEEPER_BERTH", label: "Sleeper Berth", total: "total_sleeper_berth_hours", stroke: "#4a3aa7" },
  { key: "DRIVING", label: "Driving", total: "total_driving_hours", stroke: "#1baf7a" },
  { key: "ON_DUTY", label: "On Duty", total: "total_on_duty_hours", stroke: "#eb6834" },
];

const INK = { primary: "#1d1d1f", secondary: "#6e6e73", muted: "#707075" };
const CHART = { surface: "#f5f5f7", gridline: "#e3e3e8", axis: "#c7c7cc" };

const TIME_SCALE = 24 * 60;

// The axis is dense at 1200px and unreadable once the sheet scales down, so
// label every other hour. Gridlines still mark every hour.
const HOUR_LABEL_STEP = 2;

function parseTimeToMinutes(value) {
  if (!value) return 0;
  if (value === "24:00") return TIME_SCALE;

  const [hoursPart, minutesPart = "0"] = value.split(":");
  const hours = Number(hoursPart);
  const minutes = Number(minutesPart);
  return hours * 60 + minutes;
}

function formatHourLabel(hour) {
  return `${String(hour).padStart(2, "0")}:00`;
}

/**
 * "2026-07-07" -> "Tue, Jul 7, 2026", parsed as a local date. Passing the ISO
 * string to new Date() would read it as UTC midnight and render the previous
 * day for anyone west of Greenwich.
 */
function formatLogDate(value) {
  const [year, month, day] = String(value || "").split("-").map(Number);
  if (!year || !month || !day) return value;

  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function buildStatusMap() {
  return STATUS_ROWS.reduce((accumulator, row, index) => {
    accumulator[row.key] = { ...row, index };
    return accumulator;
  }, {});
}

function formatDuration(hours) {
  return `${Number(hours || 0).toFixed(2)} hours`;
}

function getSegmentTooltip(segment, row) {
  const title = segment.label || row.label;
  const lines = [
    title,
    `Status: ${row.label}`,
    `Start: ${segment.start}`,
    `End: ${segment.end}`,
    `Duration: ${formatDuration(segment.hours)}`,
  ];
  if (segment.remark) {
    lines.push(`Location: ${segment.remark}`);
  }
  return lines.join("\n");
}

function sortByStartTime(segments) {
  return [...(segments || [])].sort(
    (left, right) => parseTimeToMinutes(left.start) - parseTimeToMinutes(right.start)
  );
}

/** Day number, date and per-status totals — plain HTML so it stays crisp and
 *  wraps on narrow screens, instead of being baked into the SVG viewBox. */
function SheetHeader({ log }) {
  return (
    <header className="eld-log-sheet__head">
      <div className="eld-log-sheet__ident">
        <p className="eld-log-sheet__day">Day {log.day_number}</p>
        <h3 className="eld-log-sheet__date">{formatLogDate(log.date)}</h3>
      </div>

      <dl className="eld-log-sheet__totals">
        {STATUS_ROWS.map((row) => (
          <div className="eld-log-sheet__total" key={row.key}>
            <dt>
              <span
                className="eld-log-sheet__total-dot"
                style={{ backgroundColor: row.stroke }}
                aria-hidden="true"
              />
              {row.label}
            </dt>
            <dd>{Number(log[row.total] || 0).toFixed(2)}h</dd>
          </div>
        ))}
      </dl>
    </header>
  );
}

function ELDLogSheetSvg({ log }) {
  const statusMap = buildStatusMap();
  const segments = sortByStartTime(log.segments);

  // The SVG now holds only the FMCSA grid, so the top margin just clears the
  // hour axis rather than a whole header block.
  const width = 1200;
  const height = 360;
  const leftMargin = 150;
  const rightMargin = 28;
  const topMargin = 34;
  const bottomMargin = 14;
  const chartWidth = width - leftMargin - rightMargin;
  const chartHeight = height - topMargin - bottomMargin;
  const rowHeight = chartHeight / STATUS_ROWS.length;
  const labelFontSize = 14;
  const hourFontSize = 12;

  function timeToX(minutes) {
    return leftMargin + (minutes / TIME_SCALE) * chartWidth;
  }

  return (
    <svg
      className="eld-log-sheet__svg"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={`FMCSA duty status grid for day ${log.day_number}`}
    >
      <rect
        x={leftMargin}
        y={topMargin}
        width={chartWidth}
        height={chartHeight}
        rx="10"
        fill={CHART.surface}
      />

      {STATUS_ROWS.map((row, rowIndex) => {
        const rowTop = topMargin + rowIndex * rowHeight;
        const rowMiddle = rowTop + rowHeight / 2;

        return (
          <g key={row.key}>
            {/* Swatch + written label: identity never rests on colour alone. */}
            <rect x="0" y={rowMiddle - 4} width="8" height="8" rx="4" fill={row.stroke} />
            <text x="18" y={rowMiddle + 5} fill={INK.primary} fontSize={labelFontSize} fontWeight="500">
              {row.label}
            </text>
            {rowIndex > 0 && (
              <line
                x1={leftMargin}
                y1={rowTop}
                x2={leftMargin + chartWidth}
                y2={rowTop}
                stroke={CHART.gridline}
                strokeWidth="1"
              />
            )}
          </g>
        );
      })}

      {Array.from({ length: 25 }, (_, hour) => {
        const x = timeToX(hour * 60);
        const isMajor = hour % 6 === 0;
        const isLabelled = hour % HOUR_LABEL_STEP === 0;
        // Pin the first and last labels inside the grid so they can't spill
        // past the edge or collide with each other.
        const anchor = hour === 0 ? "start" : hour === 24 ? "end" : "middle";

        return (
          <g key={hour}>
            {/* Recessive hairline grid: solid, one shade off the surface. */}
            <line
              x1={x}
              y1={topMargin}
              x2={x}
              y2={topMargin + chartHeight}
              stroke={isMajor ? CHART.axis : CHART.gridline}
              strokeWidth="1"
            />
            {isLabelled && (
              <text
                x={x}
                y={topMargin - 13}
                fill={isMajor ? INK.secondary : INK.muted}
                fontSize={hourFontSize}
                fontWeight={isMajor ? "600" : "400"}
                textAnchor={anchor}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {formatHourLabel(hour)}
              </text>
            )}
          </g>
        );
      })}

      {segments.map((segment, index) => {
        const row = statusMap[segment.status] || statusMap.OFF_DUTY;
        const startMinutes = parseTimeToMinutes(segment.start);
        const endMinutes = parseTimeToMinutes(segment.end);
        const durationMinutes = Math.max(endMinutes - startMinutes, 0);
        const x = timeToX(startMinutes);
        // 2px surface gap between adjacent fills instead of a border around them.
        const w = Math.max((durationMinutes / TIME_SCALE) * chartWidth - 2, 2);
        // A thin mark centred in its lane: the FMCSA form draws duty status as
        // a trace, and a saturated fill this wide would read as a heavy block.
        const h = 26;
        const y = topMargin + row.index * rowHeight + (rowHeight - h) / 2;

        // A short block can't hold its caption; letting it render anyway is
        // what smeared "Required 30-minute break" across the grid. The tooltip
        // and the remarks row below still carry the detail.
        const caption = segment.label || row.label;
        const captionFits = w > caption.length * 6.1 + 20;

        const nextSegment = segments[index + 1];
        const nextRow = nextSegment ? statusMap[nextSegment.status] : null;
        const transitionX = timeToX(parseTimeToMinutes(segment.end));
        const shouldDrawTransition =
          nextRow && nextRow.key !== row.key && transitionX <= leftMargin + chartWidth;

        // The connector joins the two lanes it actually moves between, rather
        // than ruling the whole grid — a full-height line is indistinguishable
        // from a gridline and turns a busy day into a picket fence.
        const laneCentre = (index) => topMargin + index * rowHeight + rowHeight / 2;

        return (
          <g key={`${segment.start}-${segment.end}-${index}`} tabIndex="0" aria-label={getSegmentTooltip(segment, row)}>
            <title>{getSegmentTooltip(segment, row)}</title>
            <rect x={x} y={y} width={w} height={h} rx="4" fill={row.stroke} />
            {captionFits && (
              <text x={x + 10} y={y + h / 2 + 4} fill="#ffffff" fontSize="11" fontWeight="600">
                {caption}
              </text>
            )}
            {/* The vertical connector at a duty change is part of the FMCSA
                trace, so it's a solid rule — dashing reads as "projected". */}
            {shouldDrawTransition && (
              <line
                x1={transitionX}
                y1={laneCentre(row.index)}
                x2={transitionX}
                y2={laneCentre(nextRow.index)}
                stroke={INK.muted}
                strokeWidth="1.5"
              />
            )}
          </g>
        );
      })}
    </svg>
  );
}

// The FMCSA log form carries a "Remarks" row under the grid naming the
// city/state of every change of duty status. Segments we synthesise rather than
// observe (off-duty padding, midnight continuations) carry no remark.
function RemarksRow({ log }) {
  const statusMap = buildStatusMap();
  const entries = sortByStartTime(log.segments).filter((segment) => segment.remark);

  if (!entries.length) {
    return null;
  }

  return (
    <div className="eld-log-sheet__remarks">
      <h4 className="eld-log-sheet__remarks-title">Remarks</h4>
      <ol className="eld-log-sheet__remarks-list">
        {entries.map((segment, index) => {
          const row = statusMap[segment.status] || statusMap.OFF_DUTY;
          return (
            <li className="eld-log-sheet__remark" key={`${segment.start}-${index}`}>
              <span className="eld-log-sheet__remark-swatch" style={{ backgroundColor: row.stroke }} aria-hidden="true" />
              <span className="eld-log-sheet__remark-time">{segment.start}</span>
              <span className="eld-log-sheet__remark-place">{segment.remark}</span>
              <span className="eld-log-sheet__remark-label">{segment.label || row.label}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function LogSheetCard({ log }) {
  // The PDF captures this whole card — grid plus the date and remarks that make
  // it a readable log sheet rather than an unlabelled chart.
  const cardRef = useRef(null);

  return (
    <div className="eld-log-sheet__sheet">
      <LogSheetPdfButton log={log} targetRef={cardRef} />
      <section className="eld-log-sheet__card" ref={cardRef}>
        <SheetHeader log={log} />
        {/* Below ~620px the grid scrolls sideways instead of scaling down
            until the hour labels are unreadable. */}
        <div className="eld-log-sheet__grid">
          <ELDLogSheetSvg log={log} />
        </div>
        <RemarksRow log={log} />
      </section>
    </div>
  );
}

export default function ELDLogSheet({ log, logs }) {
  const sheets = logs || (log ? [log] : []);

  if (!sheets.length) {
    return null;
  }

  return (
    <div className="eld-log-sheet" aria-label="Daily log sheets">
      {sheets.map((sheet) => (
        <LogSheetCard log={sheet} key={`${sheet.day_number}-${sheet.date}`} />
      ))}
    </div>
  );
}
