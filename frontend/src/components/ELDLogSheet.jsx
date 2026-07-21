const STATUS_ROWS = [
  { key: "OFF_DUTY", label: "Off Duty", fill: "#f1f5f9", stroke: "#64748b", text: "#0f172a" },
  { key: "SLEEPER_BERTH", label: "Sleeper Berth", fill: "#f3e8ff", stroke: "#8b5cf6", text: "#3b0764" },
  { key: "DRIVING", label: "Driving", fill: "#dcfce7", stroke: "#16a34a", text: "#14532d" },
  { key: "ON_DUTY", label: "On Duty", fill: "#ffedd5", stroke: "#f97316", text: "#7c2d12" },
];

const TIME_SCALE = 24 * 60;

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
  return [
    title,
    `Status: ${row.label}`,
    `Start: ${segment.start}`,
    `End: ${segment.end}`,
    `Duration: ${formatDuration(segment.hours)}`,
  ].join("\n");
}

function ELDLogSheetSvg({ log }) {
  const statusMap = buildStatusMap();
  const segments = [...(log.segments || [])].sort(
    (left, right) => parseTimeToMinutes(left.start) - parseTimeToMinutes(right.start)
  );

  const width = 1200;
  const height = 420;
  const leftMargin = 160;
  const rightMargin = 28;
  const topMargin = 78;
  const bottomMargin = 44;
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
      aria-label={`FMCSA daily log sheet for day ${log.day_number}`}
    >
      <rect x="0" y="0" width={width} height={height} rx="20" fill="#ffffff" />

      <text x={leftMargin} y="34" fill="#0f172a" fontSize="18" fontWeight="700">
        Day {log.day_number} - {log.date}
      </text>
      <text x={leftMargin} y="56" fill="#475569" fontSize="12">
        Driving {log.total_driving_hours}h | On Duty {log.total_on_duty_hours}h | Off Duty {log.total_off_duty_hours}h | Sleeper {log.total_sleeper_berth_hours}h
      </text>

      <g transform={`translate(${leftMargin}, 24)`}>
        {STATUS_ROWS.map((row, index) => (
          <g key={row.key} transform={`translate(${index * 132}, 0)`}>
            <rect x="0" y="0" width="120" height="20" rx="10" fill={row.fill} stroke={row.stroke} />
            <circle cx="14" cy="10" r="5" fill={row.stroke} />
            <text x="24" y="14" fill={row.text} fontSize="10" fontWeight="700">
              {row.label}
            </text>
          </g>
        ))}
      </g>

      <rect
        x={leftMargin}
        y={topMargin}
        width={chartWidth}
        height={chartHeight}
        rx="14"
        fill="#f8fafc"
        stroke="#cbd5e1"
      />

      {STATUS_ROWS.map((row, rowIndex) => {
        const rowTop = topMargin + rowIndex * rowHeight;
        const rowMiddle = rowTop + rowHeight / 2;

        return (
          <g key={row.key}>
            <rect x="18" y={rowTop} width={leftMargin - 32} height={rowHeight} fill={row.fill} stroke="none" />
            <text x="30" y={rowMiddle + 5} fill={row.text} fontSize={labelFontSize} fontWeight="700">
              {row.label}
            </text>
            <line
              x1={leftMargin}
              y1={rowTop}
              x2={leftMargin + chartWidth}
              y2={rowTop}
              stroke="#dbe4ef"
              strokeWidth="1"
            />
          </g>
        );
      })}

      {Array.from({ length: 25 }, (_, hour) => {
        const x = timeToX(hour * 60);
        const labelX = hour === 24 ? x - 6 : x;
        return (
          <g key={hour}>
            <line
              x1={x}
              y1={topMargin}
              x2={x}
              y2={topMargin + chartHeight}
              stroke={hour % 6 === 0 ? "#94a3b8" : "#d4d4d8"}
              strokeWidth={hour % 6 === 0 ? "1.5" : "1"}
            />
            <text
              x={labelX}
              y="22"
              fill="#1e293b"
              fontSize={hourFontSize}
              fontWeight={hour % 6 === 0 ? "700" : "500"}
              textAnchor={hour === 24 ? "end" : "middle"}
            >
              {formatHourLabel(hour)}
            </text>
          </g>
        );
      })}

      {segments.map((segment, index) => {
        const row = statusMap[segment.status] || statusMap.OFF_DUTY;
        const startMinutes = parseTimeToMinutes(segment.start);
        const endMinutes = parseTimeToMinutes(segment.end);
        const durationMinutes = Math.max(endMinutes - startMinutes, 0);
        const x = timeToX(startMinutes);
        const w = Math.max((durationMinutes / TIME_SCALE) * chartWidth, 2);
        const y = topMargin + row.index * rowHeight + 8;
        const h = rowHeight - 16;

        const nextSegment = segments[index + 1];
        const transitionX = index < segments.length - 1 ? timeToX(parseTimeToMinutes(segment.end)) : null;
        const shouldDrawTransition =
          transitionX !== null && nextSegment && nextSegment.status !== segment.status && transitionX < leftMargin + chartWidth;

        return (
          <g key={`${segment.start}-${segment.end}-${index}`} tabIndex="0" aria-label={getSegmentTooltip(segment, row)}>
            <title>{getSegmentTooltip(segment, row)}</title>
            <rect x={x} y={y} width={w} height={h} rx="7" fill={row.stroke} opacity="0.85" />
            <text x={x + 8} y={y + h / 2 + 4} fill="#ffffff" fontSize="11" fontWeight="700">
              {segment.label || row.label}
            </text>
            {shouldDrawTransition && (
              <line
                x1={transitionX}
                y1={topMargin + 2}
                x2={transitionX}
                y2={topMargin + chartHeight - 2}
                stroke="#475569"
                strokeWidth="1.5"
                strokeDasharray="4 3"
              />
            )}
          </g>
        );
      })}

      <line
        x1={leftMargin}
        y1={topMargin + chartHeight}
        x2={leftMargin + chartWidth}
        y2={topMargin + chartHeight}
        stroke="#94a3b8"
        strokeWidth="1"
      />
    </svg>
  );
}

export default function ELDLogSheet({ log, logs }) {
  const sheets = logs || (log ? [log] : []);

  if (!sheets.length) {
    return null;
  }

  return (
    <div className="eld-log-sheet" aria-label="Daily log sheets">
      <div className="eld-log-sheet__legend" aria-label="Duty status legend">
        {STATUS_ROWS.map((row) => (
          <div className="eld-log-sheet__legend-item" key={row.key}>
            <span className="eld-log-sheet__legend-swatch" style={{ backgroundColor: row.stroke }} aria-hidden="true" />
            <span>{row.label}</span>
          </div>
        ))}
      </div>
      {sheets.map((sheet) => (
        <section className="eld-log-sheet__card" key={`${sheet.day_number}-${sheet.date}`}>
          <ELDLogSheetSvg log={sheet} />
        </section>
      ))}
    </div>
  );
}