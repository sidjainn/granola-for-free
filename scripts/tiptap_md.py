"""Render Granola TipTap (ProseMirror) JSON to markdown.

Handles the node types Granola uses in panel content: heading, paragraph,
bulletList / orderedList / listItem, text with bold/italic/code/link marks,
hardBreak, blockquote, codeBlock.
"""
from __future__ import annotations

from typing import Any


def _marks_open_close(marks: list[dict]) -> tuple[str, str]:
    open_, close = "", ""
    for m in marks or []:
        t = m.get("type")
        if t == "bold":
            open_ += "**"
            close = "**" + close
        elif t == "italic":
            open_ += "*"
            close = "*" + close
        elif t == "code":
            open_ += "`"
            close = "`" + close
        elif t == "link":
            href = (m.get("attrs") or {}).get("href", "")
            open_ += "["
            close = f"]({href})" + close
        elif t == "strike":
            open_ += "~~"
            close = "~~" + close
    return open_, close


def _inline(node: dict) -> str:
    t = node.get("type")
    if t == "text":
        text = node.get("text", "")
        o, c = _marks_open_close(node.get("marks") or [])
        return f"{o}{text}{c}"
    if t == "hardBreak":
        return "  \n"
    # Unknown inline → recurse into content if any
    parts = [_inline(c) for c in node.get("content") or []]
    return "".join(parts)


def _render_block(node: dict, depth: int = 0) -> str:
    t = node.get("type")
    children = node.get("content") or []

    if t in ("doc", None):
        return "\n\n".join(s for s in (_render_block(c, depth) for c in children) if s.strip())

    if t == "heading":
        level = (node.get("attrs") or {}).get("level", 2)
        text = "".join(_inline(c) for c in children)
        return f"{'#' * max(1, min(6, level))} {text}".rstrip()

    if t == "paragraph":
        text = "".join(_inline(c) for c in children)
        return text

    if t == "blockquote":
        inner = _render_block({"type": "doc", "content": children}, depth)
        return "\n".join("> " + ln for ln in inner.splitlines())

    if t == "codeBlock":
        lang = (node.get("attrs") or {}).get("language", "")
        text = "".join(_inline(c) for c in children)
        return f"```{lang}\n{text}\n```"

    if t == "bulletList":
        return "\n".join(_render_list_item(c, depth, ordered=False) for c in children)

    if t == "orderedList":
        return "\n".join(_render_list_item(c, depth, ordered=True, idx=i + 1) for i, c in enumerate(children))

    if t == "horizontalRule":
        return "---"

    # Fallback: just join inline of children.
    return "".join(_inline(c) for c in children)


def _render_list_item(node: dict, depth: int, ordered: bool, idx: int = 1) -> str:
    bullet = f"{idx}." if ordered else "-"
    indent = "  " * depth
    children = node.get("content") or []
    if not children:
        return f"{indent}{bullet} "
    # First block goes on the bullet line.
    first = children[0]
    rest = children[1:]
    first_rendered = _render_block(first, depth + 1)
    first_line, *first_more = first_rendered.split("\n")
    out = [f"{indent}{bullet} {first_line}"]
    for ln in first_more:
        out.append(f"{indent}  {ln}")
    for r in rest:
        sub = _render_block(r, depth + 1)
        for ln in sub.splitlines():
            out.append(f"{indent}  {ln}")
    return "\n".join(out)


def render(doc: Any) -> str:
    if not isinstance(doc, dict):
        return ""
    md = _render_block(doc)
    # collapse 3+ blank lines.
    while "\n\n\n" in md:
        md = md.replace("\n\n\n", "\n\n")
    return md.strip()
