import AnswerNotice from "./AnswerNotice.jsx";
import StreamingAnswer from "./StreamingAnswer.jsx";
import Thinking from "./Thinking.jsx";

export default function Exchange({ exchange, onAsk, busy }) {
  return (
    <section className="exchange">
      <div className="ask">
        <span className="ask__label">You asked</span>
        <p className="ask__text">{exchange.question}</p>
      </div>

      {exchange.status === "pending" && <Thinking stage={exchange.stage} />}

      {exchange.status === "streaming" && (
        <StreamingAnswer id={exchange.id} text={exchange.streamText} />
      )}

      {exchange.status === "error" && (
        <div className="notice notice--error" role="alert">
          <p className="notice__kind">Couldn’t get an answer</p>
          <p className="notice__text">{exchange.error}</p>
          <p className="notice__hint">Check the API is running, then ask again.</p>
        </div>
      )}

      {exchange.status === "done" && (
        <AnswerNotice exchange={exchange} onAsk={onAsk} busy={busy} />
      )}
    </section>
  );
}
