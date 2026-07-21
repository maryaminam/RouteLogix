import { useState } from "react";

/**
 * Exports one day's log sheet card to a single-page PDF.
 *
 * html2canvas and jsPDF together are ~500kB — far larger than the rest of the
 * app — so they're imported on first click rather than shipped in the initial
 * bundle.
 */
async function loadExporters() {
  const [html2canvas, jspdf] = await Promise.all([
    import("html2canvas"),
    import("jspdf"),
  ]);
  return { html2canvas: html2canvas.default, jsPDF: jspdf.jsPDF };
}

// Captured width, independent of the viewport. Two reasons it's fixed:
// the grid sits in an overflow-x scroller that would otherwise crop the export
// to whatever is scrolled into view, and capturing at the device width would
// make a phone export a 320px-wide sheet stretched blurrily across A4.
const EXPORT_WIDTH = 1180;

/**
 * Renders `source` off-screen at EXPORT_WIDTH and hands the detached copy to
 * `capture`. Working on a clone keeps the visible card untouched — no width
 * flash mid-export, and nothing to restore if the capture throws.
 */
async function withExportClone(source, capture) {
  const holder = document.createElement("div");
  holder.setAttribute("aria-hidden", "true");
  holder.style.cssText = `position:absolute;top:0;left:-100000px;width:${EXPORT_WIDTH}px;`;

  const clone = source.cloneNode(true);
  clone.classList.add("is-exporting");
  holder.appendChild(clone);
  document.body.appendChild(holder);

  try {
    return await capture(clone);
  } finally {
    holder.remove();
  }
}

export default function LogSheetPdfButton({ log, targetRef }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const filename = `log-day-${log.day_number}-${log.date}.pdf`;

  async function handleDownload() {
    const node = targetRef.current;
    if (!node || busy) return;

    setBusy(true);
    setError(null);

    try {
      const { html2canvas, jsPDF } = await loadExporters();

      const canvas = await withExportClone(node, (clone) =>
        html2canvas(clone, {
          backgroundColor: "#ffffff",
          // 2x so the grid's hairlines and 11px captions stay legible in print.
          scale: 2,
          useCORS: true,
          width: EXPORT_WIDTH,
          windowWidth: EXPORT_WIDTH,
        })
      );

      // A 24-hour grid is far wider than it is tall, so landscape wastes the
      // least paper. Fit to the page, then centre what's left over.
      // compress: true matters here — without it jsPDF stores the bitmap as raw
      // RGB, which turns a flat-colour grid into a ~7MB file per day.
      const pdf = new jsPDF({ orientation: "landscape", unit: "pt", format: "a4", compress: true });
      const pageWidth = pdf.internal.pageSize.getWidth();
      const pageHeight = pdf.internal.pageSize.getHeight();
      const margin = 24;

      const scale = Math.min(
        (pageWidth - margin * 2) / canvas.width,
        (pageHeight - margin * 2) / canvas.height
      );
      const renderWidth = canvas.width * scale;
      const renderHeight = canvas.height * scale;

      pdf.addImage(
        canvas.toDataURL("image/png"),
        "PNG",
        (pageWidth - renderWidth) / 2,
        (pageHeight - renderHeight) / 2,
        renderWidth,
        renderHeight
      );
      pdf.save(filename);
    } catch (err) {
      setError("Couldn't build the PDF. Try again.");
      console.error("Log sheet PDF export failed:", err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="log-sheet-export">
      <button
        type="button"
        className="log-sheet-export__button"
        onClick={handleDownload}
        disabled={busy}
        aria-label={`Download the day ${log.day_number} log sheet as a PDF`}
      >
        {busy ? "Preparing…" : "Download as PDF"}
      </button>
      {error && (
        <span className="log-sheet-export__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
