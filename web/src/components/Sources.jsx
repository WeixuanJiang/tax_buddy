function host(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export default function Sources({ exchangeId, citations, related }) {
  const hasCitations = citations && citations.length > 0;
  const hasRelated = related && related.length > 0;
  if (!hasCitations && !hasRelated) return null;

  return (
    <div className="ledger">
      {hasCitations && (
        <section className="ledger__block" aria-label="Sources">
          <h3 className="ledger__title">Sources</h3>
          <ol className="ledger__list" role="list">
            {citations.map((c) => (
              <li
                key={c.n}
                id={`src-${exchangeId}-${c.n}`}
                className="source"
              >
                <span className="source__n" aria-hidden="true">
                  {c.n}
                </span>
                <a
                  className="source__link"
                  href={c.url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <span className="source__title">{c.title || host(c.url)}</span>
                  <span className="source__host">{host(c.url)} ↗</span>
                </a>
              </li>
            ))}
          </ol>
        </section>
      )}

      {hasRelated && (
        <section className="ledger__block" aria-label="Related ATO pages">
          <h3 className="ledger__title">Related</h3>
          <ul className="related" role="list">
            {related.map((r) => (
              <li key={r.url}>
                <a href={r.url} target="_blank" rel="noopener noreferrer">
                  {r.title || host(r.url)}
                </a>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
