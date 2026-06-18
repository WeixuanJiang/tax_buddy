import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { markdownComponents } from "../lib/markdown.jsx";

// Progressive answer render while tokens stream in. Sources/disclaimer are added
// once the final `done` event arrives (AnswerNotice takes over then).
export default function StreamingAnswer({ id, text }) {
  return (
    <div className="notice">
      <div className="notice__body markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents(id)}>
          {text}
        </ReactMarkdown>
        <span className="caret" aria-hidden="true" />
      </div>
    </div>
  );
}
