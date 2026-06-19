const DEFAULT_EXAMPLES = [
  "How do I amend my tax return after lodging?",
  "What can I claim for working from home?",
  "I'm a nurse — what work-related expenses can I claim?",
  "How does the capital gains tax discount work?",
  "Can I claim a deduction for personal super contributions?",
  "What is the Medicare levy and what rate do I pay?",
];

function article(word) {
  return /^[aeiou]/i.test(word) ? "an" : "a";
}

// Tailor the starter questions to the signed-in user's occupation.
function examplesFor(occupation) {
  const occ = (occupation || "").trim();
  if (!occ) return DEFAULT_EXAMPLES;
  const a = article(occ);
  return [
    `What work-related expenses can I claim as ${a} ${occ}?`,
    `Can I claim tools, equipment, or a uniform as ${a} ${occ}?`,
    `What car and travel expenses can I claim as ${a} ${occ}?`,
    `What self-education or training can ${a} ${occ} deduct?`,
    "What can I claim for working from home?",
    "How does the capital gains tax discount work?",
  ];
}

export default function EmptyState({ onPick, occupation, suggestions }) {
  // Prefer the AI-recommended questions from the server (generated once per user
  // and cached in the DB); fall back to local templates while they load or if the
  // request failed.
  const examples =
    Array.isArray(suggestions) && suggestions.length
      ? suggestions
      : examplesFor(occupation);
  const occ = (occupation || "").trim();
  const label = occ ? `Suggested for your work as ${article(occ)} ${occ}` : "Try one of these";

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
        <p className="empty__examples-label">{label}</p>
        <ul className="chiprow" role="list">
          {examples.map((q) => (
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
