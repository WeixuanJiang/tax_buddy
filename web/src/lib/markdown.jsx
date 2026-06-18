import { linkifyChildren } from "./citations.jsx";

// react-markdown element renderers shared by the streamed preview and the final
// answer: inline [n] markers become clickable citations; tables get a scroll
// wrapper; links open in a new tab.
export function markdownComponents(exchangeId) {
  const cite = (Tag) =>
    function Renderer({ children }) {
      return <Tag>{linkifyChildren(children, exchangeId)}</Tag>;
    };
  return {
    p: cite("p"),
    li: cite("li"),
    td: cite("td"),
    th: cite("th"),
    a: ({ href, children }) => (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    ),
    table: ({ children }) => (
      <div className="tablewrap">
        <table>{children}</table>
      </div>
    ),
  };
}
