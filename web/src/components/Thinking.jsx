// Skeleton shown before the answer starts streaming. Shows the agent's current
// stage (e.g. "Searching ATO content") so the wait reads as progress.
export default function Thinking({ stage }) {
  return (
    <div className="thinking" role="status" aria-live="polite">
      <span className="thinking__label">
        <span className="thinking__pulse" aria-hidden="true" />
        {stage || "Working…"}
      </span>
      <div className="thinking__lines" aria-hidden="true">
        <span style={{ width: "92%" }} />
        <span style={{ width: "78%" }} />
        <span style={{ width: "85%" }} />
        <span style={{ width: "40%" }} />
      </div>
    </div>
  );
}
