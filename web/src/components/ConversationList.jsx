export default function ConversationList({ items, activeId, onSelect, onNew, onDelete, busy }) {
  return (
    <aside className="history">
      <button className="history__new" onClick={onNew} disabled={busy}>+ New chat</button>
      <ul className="history__list">
        {items.map((c) => (
          <li
            key={c.thread_id}
            className={"history__item" + (c.thread_id === activeId ? " is-active" : "")}
          >
            <button className="history__open" onClick={() => onSelect(c.thread_id)} title={c.title}>
              {c.title}
            </button>
            <button
              className="history__del"
              onClick={() => onDelete(c.thread_id)}
              aria-label="Delete conversation"
            >×</button>
          </li>
        ))}
        {items.length === 0 && <li className="history__empty">No conversations yet</li>}
      </ul>
    </aside>
  );
}
