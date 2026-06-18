const EXAMPLES = [
  "How do I amend my tax return after lodging?",
  "What can I claim for working from home?",
  "I'm a nurse — what work-related expenses can I claim?",
  "How does the capital gains tax discount work?",
  "Can I claim a deduction for personal super contributions?",
  "What is the Medicare levy and what rate do I pay?",
];

export default function EmptyState({ onPick }) {
  return (
    <section className="empty" aria-labelledby="empty-title">
      <p className="empty__eyebrow">Australian individual tax returns</p>
      <h2 id="empty-title" className="empty__headline">
        Ask a question. Get an answer you can trace back to the&nbsp;ATO.
      </h2>
      <p className="empty__lede">
        Every answer is drawn from ATO website content, cites its sources, and
        tells you the income year it applies to. It’s general information — not
        advice about your situation.
      </p>

      <div className="empty__examples">
        <p className="empty__examples-label">Try one of these</p>
        <ul className="chiprow" role="list">
          {EXAMPLES.map((q) => (
            <li key={q}>
              <button type="button" className="chip" onClick={() => onPick(q)}>
                {q}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
