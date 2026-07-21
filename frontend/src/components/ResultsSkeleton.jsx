function Block({ className }) {
  return <div className={`skeleton__block ${className}`} aria-hidden="true" />;
}

/**
 * Placeholder mirroring the shape of the real dashboard (status card, map,
 * summary, log sheets) so the layout doesn't jump when results arrive.
 */
export default function ResultsSkeleton() {
  return (
    <div className="results results--dashboard skeleton" role="status" aria-live="polite">
      <span className="visually-hidden">Planning trip, please wait…</span>

      <section className="skeleton__card skeleton__card--status">
        <Block className="skeleton__block--eyebrow" />
        <Block className="skeleton__block--title" />
        <div className="skeleton__grid">
          {Array.from({ length: 4 }, (_, index) => (
            <Block key={index} className="skeleton__block--metric" />
          ))}
        </div>
      </section>

      <section className="skeleton__card skeleton__card--map">
        <div className="skeleton__map">
          <span className="skeleton__spinner" aria-hidden="true" />
          <p className="skeleton__caption">Routing the trip and applying hours-of-service rules…</p>
        </div>
      </section>

      <section className="skeleton__card">
        <Block className="skeleton__block--eyebrow" />
        <div className="skeleton__grid">
          {Array.from({ length: 3 }, (_, index) => (
            <Block key={index} className="skeleton__block--metric" />
          ))}
        </div>
      </section>

      <section className="skeleton__card">
        <Block className="skeleton__block--eyebrow" />
        <Block className="skeleton__block--sheet" />
        <Block className="skeleton__block--sheet" />
      </section>
    </div>
  );
}
