"""Turn a page's `content_blocks` into retrieval chunks.

Strategy (see plan): group blocks under their heading into sections, render each
block to text, keep every table whole (as markdown), then greedily pack a section's
pieces into chunks up to a token budget. Each chunk is prefixed with the page
breadcrumb + heading path so it is self-describing when retrieved in isolation.
"""
from __future__ import annotations

from dataclasses import dataclass, field

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")

    def ntok(s: str) -> int:
        return len(_ENC.encode(s))
except Exception:  # pragma: no cover - fallback if tiktoken unavailable
    def ntok(s: str) -> int:
        return max(1, len(s) // 4)

MAX_TOKENS = 500     # target upper bound per chunk
MIN_TOKENS = 40      # below this a chunk is merged forward (unless it has a table)


@dataclass
class Chunk:
    heading: str
    breadcrumb: str
    chunk_text: str
    has_table: bool = False
    token_count: int = 0


# ---- block rendering -------------------------------------------------------

def _render_list(block: dict) -> str:
    ordered = block.get("ordered")
    out = []
    for i, item in enumerate(block.get("items", []), 1):
        out.append(f"{i}. {item}" if ordered else f"- {item}")
    return "\n".join(out)


def _render_table(block: dict) -> str:
    rows = block.get("rows", [])
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    md = ["| " + " | ".join(header) + " |",
          "| " + " | ".join(["---"] * width) + " |"]
    for r in body:
        md.append("| " + " | ".join(r) + " |")
    return "\n".join(md)


def _piece(block: dict) -> tuple[str, bool]:
    """Return (text, is_table) for a non-heading block."""
    t = block["type"]
    if t == "paragraph":
        return block.get("text", ""), False
    if t == "list":
        return _render_list(block), False
    if t == "table":
        return _render_table(block), True
    return "", False


# ---- sectioning ------------------------------------------------------------

@dataclass
class _Section:
    heading_path: str
    pieces: list[tuple[str, bool]] = field(default_factory=list)  # (text, is_table)


def _sections(blocks: list[dict]) -> list[_Section]:
    headings: dict[int, str] = {}
    sections: list[_Section] = []
    cur = _Section(heading_path="")
    for b in blocks:
        if b["type"] == "heading":
            if cur.pieces:
                sections.append(cur)
            lvl = int(b.get("level", 2))
            headings[lvl] = b.get("text", "")
            for deeper in [k for k in headings if k > lvl]:
                headings.pop(deeper, None)
            path = " / ".join(headings[k] for k in sorted(headings))
            cur = _Section(heading_path=path)
        else:
            text, _ = _piece(b)
            if text.strip():
                cur.pieces.append(_piece(b))
    if cur.pieces:
        sections.append(cur)
    return sections


# ---- packing ---------------------------------------------------------------

def chunk_document(doc: dict, breadcrumb: str) -> list[Chunk]:
    blocks = doc.get("content_blocks", [])
    chunks: list[Chunk] = []
    prefix_base = f"[{breadcrumb}]" if breadcrumb else ""

    for sec in _sections(blocks):
        head_label = sec.heading_path
        prefix = f"{prefix_base} {head_label}".strip()
        buf: list[str] = []
        buf_tok = 0
        buf_table = False

        def flush():
            nonlocal buf, buf_tok, buf_table
            if not buf:
                return
            body = "\n\n".join(buf)
            text = f"{prefix}\n{body}" if prefix else body
            chunks.append(Chunk(
                heading=head_label, breadcrumb=breadcrumb, chunk_text=text,
                has_table=buf_table, token_count=ntok(text),
            ))
            buf, buf_tok, buf_table = [], 0, False

        for text, is_table in sec.pieces:
            tks = ntok(text)
            # a single oversized/table piece becomes its own chunk
            if tks >= MAX_TOKENS:
                flush()
                t = f"{prefix}\n{text}" if prefix else text
                chunks.append(Chunk(head_label, breadcrumb, t, is_table, ntok(t)))
                continue
            if buf_tok + tks > MAX_TOKENS:
                flush()
            buf.append(text)
            buf_tok += tks
            buf_table = buf_table or is_table
        flush()

    # merge tiny trailing chunks (no table) into the previous chunk
    merged: list[Chunk] = []
    for c in chunks:
        if (merged and not c.has_table and c.token_count < MIN_TOKENS
                and merged[-1].heading == c.heading):
            prev = merged[-1]
            prev.chunk_text += "\n\n" + c.chunk_text.split("\n", 1)[-1]
            prev.token_count = ntok(prev.chunk_text)
        else:
            merged.append(c)
    return merged
