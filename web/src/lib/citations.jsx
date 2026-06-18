// Turn inline [n] markers in the answer markdown into clickable references that
// jump to the matching entry in the source ledger.
const CITE = /\[(\d+)\]/g;

function jumpTo(id) {
  const el = document.getElementById(id);
  if (!el) return;
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.remove("source--flash");
  // reflow so the animation can retrigger
  void el.offsetWidth;
  el.classList.add("source--flash");
}

function linkifyString(str, keyBase, exchangeId) {
  const out = [];
  let last = 0;
  let m;
  CITE.lastIndex = 0;
  while ((m = CITE.exec(str)) !== null) {
    if (m.index > last) out.push(str.slice(last, m.index));
    const n = m[1];
    const id = `src-${exchangeId}-${n}`;
    out.push(
      <sup key={`${keyBase}-${m.index}`} className="cite-wrap">
        <a
          className="cite"
          href={`#${id}`}
          onClick={(e) => {
            e.preventDefault();
            jumpTo(id);
          }}
          aria-label={`Go to source ${n}`}
        >
          {n}
        </a>
      </sup>
    );
    last = m.index + m[0].length;
  }
  if (last < str.length) out.push(str.slice(last));
  return out;
}

// Recursively process react-markdown children, rewriting [n] inside text nodes.
export function linkifyChildren(children, exchangeId, keyBase = "c") {
  const arr = Array.isArray(children) ? children : [children];
  return arr.flatMap((child, i) => {
    if (typeof child === "string") {
      return linkifyString(child, `${keyBase}-${i}`, exchangeId);
    }
    return [child];
  });
}
