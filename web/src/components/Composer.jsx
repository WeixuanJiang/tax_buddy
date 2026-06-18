import { useEffect, useRef, useState } from "react";

export default function Composer({ onSend, busy }) {
  const [value, setValue] = useState("");
  const ref = useRef(null);

  // Auto-grow the textarea to fit its content, up to a cap.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  function submit() {
    const q = value.trim();
    if (!q || busy) return;
    onSend(q);
    setValue("");
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <form
      className="composer"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="composer__field">
        <textarea
          ref={ref}
          className="composer__input"
          rows={1}
          placeholder="Ask about your tax return…"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          aria-label="Your tax-return question"
        />
        <button
          type="submit"
          className="composer__send"
          disabled={!value.trim() || busy}
          aria-label="Send question"
        >
          {busy ? (
            <span className="composer__spinner" aria-hidden="true" />
          ) : (
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path
                d="M4 12h13M11 6l6 6-6 6"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          )}
        </button>
      </div>
      <p className="composer__hint">
        Press Enter to send · Shift + Enter for a new line. Individual tax returns
        only.
      </p>
    </form>
  );
}
