import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents } from "../lib/markdown.jsx";
import Sources from "./Sources.jsx";

const DISCLAIMER =
  "This is general information based on ATO website content, not personal tax, " +
  "financial or legal advice. For advice about your situation, consult a " +
  "registered tax agent or the ATO.";

// The API appends a year line + disclaimer to the answer text; lift them out so
// they can be presented as designed chrome instead of raw prose.
function splitAnswer(text) {
  if (!text) return { body: "", year: "" };
  let body = text;
  let year = "";
  const yearMatch = body.match(/_Applies to the (.+?) income year\._/i);
  if (yearMatch) year = yearMatch[1];
  body = body
    .replace(/\n*_Applies to the .+? income year\._\n*/i, "\n")
    .replace(/This is general information based on ATO website content[\s\S]*$/i, "")
    .replace(/\n*_Note:[\s\S]*?verify\._/i, (m) => m) // keep verify note inline
    .trim();
  return { body, year };
}

export default function AnswerNotice({ exchange, onAsk, busy }) {
  const { route, answer, citations, related_links, income_year, suggestions } =
    exchange;

  if (route === "refuse") {
    return (
      <div className="notice notice--aside" role="note">
        <p className="notice__kind">Outside scope</p>
        <div className="notice__text markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents(exchange.id)}
          >
            {answer}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  if (route === "clarify") {
    return (
      <div className="notice notice--ask" role="note">
        <p className="notice__kind">One quick thing</p>
        <div className="notice__text markdown">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={markdownComponents(exchange.id)}
          >
            {answer}
          </ReactMarkdown>
        </div>
      </div>
    );
  }

  const { body, year } = splitAnswer(answer);
  const yearLabel = year || income_year;

  return (
    <article className="notice">
      <div className="notice__body markdown">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={markdownComponents(exchange.id)}
        >
          {body}
        </ReactMarkdown>
      </div>

      <Sources
        exchangeId={exchange.id}
        citations={citations}
        related={related_links}
      />

      {suggestions && suggestions.length > 0 && (
        <nav className="followups" aria-label="Suggested follow-up questions">
          <p className="followups__label">Ask next</p>
          <ul className="chiprow" role="list">
            {suggestions.map((q) => (
              <li key={q}>
                <button
                  type="button"
                  className="chip chip--ask"
                  onClick={() => onAsk?.(q)}
                  disabled={busy}
                >
                  {q}
                  <span className="chip__arrow" aria-hidden="true">→</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>
      )}

      <footer className="notice__foot">
        {yearLabel && (
          <span className="yeartag yeartag--inline">{yearLabel} income year</span>
        )}
        <p className="disclaimer">
          <span className="disclaimer__dot" aria-hidden="true" />
          {DISCLAIMER}
        </p>
      </footer>
    </article>
  );
}
