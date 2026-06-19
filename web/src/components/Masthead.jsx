export default function Masthead({
  taxYear,
  onReset,
  canReset,
  thinking,
  onToggleThinking,
  authControl,
}) {
  return (
    <header className="masthead">
      <div className="masthead__id">
        <span className="masthead__mark" aria-hidden="true">§</span>
        <div className="masthead__titles">
          <h1 className="masthead__title">Tax Buddy</h1>
          <p className="masthead__sub">General information from ATO content</p>
        </div>
      </div>
      <div className="masthead__meta">
        {taxYear && (
          <span className="yeartag" title="Answers apply to this income year">
            {taxYear} income year
          </span>
        )}
        <button
          type="button"
          className={`toggle${thinking ? " toggle--on" : ""}`}
          role="switch"
          aria-checked={thinking}
          onClick={onToggleThinking}
          title="When on, the model reasons step-by-step before answering (slower, deeper)"
        >
          <span className="toggle__track" aria-hidden="true">
            <span className="toggle__thumb" />
          </span>
          <span className="toggle__label">Thinking</span>
        </button>
        <button
          type="button"
          className="btn-ghost"
          onClick={onReset}
          disabled={!canReset}
        >
          New question
        </button>
        {authControl}
      </div>
    </header>
  );
}
