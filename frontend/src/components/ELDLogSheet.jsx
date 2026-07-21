const STATUS_ROWS = [
  { key: "OFF_DUTY", label: "Off Duty", fill: "#f8fafc", stroke: "#94a3b8", text: "#0f172a" },
  { key: "SLEEPER_BERTH", label: "Sleeper Berth", fill: "#eef2ff", stroke: "#818cf8", text: "#1e1b4b" },
  { key: "DRIVING", label: "Driving", fill: "#ecfdf5", stroke: "#10b981", text: "#064e3b" },
  { key: "ON_DUTY", label: "On Duty", fill: "#fff7ed", stroke: "#f97316", text: "#7c2d12" },
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

function ELDLogSheetSvg({ log }) {
  const statusMap = buildStatusMap();
  const segments = [...(log.segments || [])].sort(
    (left, right) => parseTimeToMinutes(left.start) - parseTimeToMinutes(right.start)
  );

  const width = 1200;
  const height = 420;
  const leftMargin = 160;
  const rightMargin = 28;
  const topMargin = 70;
  const bottomMargin = 44;
  const chartWidth = width - leftMargin - rightMargin;
  const chartHeight = height - topMargin - bottomMargin;
  const rowHeight = chartHeight / STATUS_ROWS.length;
  const labelFontSize = 13;
  const hourFontSize = 11;

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
      <text x={leftMargin} y="55" fill="#475569" fontSize="12">
        Driving {log.total_driving_hours}h | On Duty {log.total_on_duty_hours}h | Off Duty {log.total_off_duty_hours}h | Sleeper {log.total_sleeper_berth_hours}h
      </text>

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
            <text x="30" y={rowMiddle + 5} fill={row.text} fontSize={labelFontSize} fontWeight="600">
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
              stroke={hour % 6 === 0 ? "#94a3b8" : "#cbd5e1"}
              strokeWidth={hour % 6 === 0 ? "1.5" : "1"}
            />
            <text x={labelX} y="22" fill="#334155" fontSize={hourFontSize} textAnchor={hour === 24 ? "end" : "middle"}>
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
          <g key={`${segment.start}-${segment.end}-${index}`}>
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
    <div className="eld-log-sheet">
      {sheets.map((sheet) => (
        <section className="eld-log-sheet__card" key={`${sheet.day_number}-${sheet.date}`}>
          <ELDLogSheetSvg log={sheet} />
        </section>
      ))}
    </div>
  );
}