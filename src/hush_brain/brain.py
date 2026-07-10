"""The Brain: a plain-markdown memory vault with two-tier recall.

Inspired by claude-obsidian: `hot.md` is a rolling recent-context cache (~500 words),
`index.md` is the master catalog (one line per memory), and `memories/*.md` hold one
fact each. Recall reads hot -> index -> targeted pages and cites `[[slug]]`.
Plain files, zero lock-in.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

HOT_WORD_CAP = 500
TITLE_MAX = 120


def clean_title(title: str) -> str:
    """One line, bounded length — a newline or '---' in a title must never
    corrupt frontmatter or index.md."""
    title = re.sub(r"\s+", " ", str(title)).strip()
    return title[:TITLE_MAX] or "untitled"


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:60] or "memory"


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2}


class Brain:
    def __init__(self, root: Path | str):
        self.root = Path(root)
        self.memories_dir = self.root / "memories"
        self.hot_path = self.root / "hot.md"
        self.index_path = self.root / "index.md"
        self.memories_dir.mkdir(parents=True, exist_ok=True)
        if not self.hot_path.exists():
            self.hot_path.write_text("# hot cache\n", encoding="utf-8")
        if not self.index_path.exists():
            self.index_path.write_text("# index\n", encoding="utf-8")

    # -- write ---------------------------------------------------------------

    def remember(self, title: str, content: str, tags: list[str] | None = None) -> dict:
        title = clean_title(title)
        slug = slugify(title)
        path = self.memories_dir / f"{slug}.md"
        n = 2
        while path.exists():
            slug_n = f"{slug}-{n}"
            path = self.memories_dir / f"{slug_n}.md"
            n += 1
        slug = path.stem
        created = time.strftime("%Y-%m-%d %H:%M:%S")
        tag_line = ", ".join(re.sub(r"[^\w-]", "", t) for t in (tags or []))
        # json.dumps produces a valid YAML double-quoted scalar (quotes escaped)
        path.write_text(
            f"---\ntitle: {json.dumps(title, ensure_ascii=False)}\ncreated: {created}\ntags: [{tag_line}]\n---\n\n{content}\n",
            encoding="utf-8",
        )
        hook = re.sub(r"\s+", " ", content).strip()[:100]
        with self.index_path.open("a", encoding="utf-8") as f:
            f.write(f"- [[{slug}]] — {title} — {hook}\n")
        self._update_hot(f"[[{slug}]] {title}: {hook}")
        return {"slug": slug, "title": title, "path": str(path)}

    def _update_hot(self, line: str) -> None:
        body = self.hot_path.read_text(encoding="utf-8").splitlines()
        header, entries = body[:1], body[1:]
        entries.insert(0, f"- {line}")
        kept, words = [], 0
        for entry in entries:
            words += len(entry.split())
            if words > HOT_WORD_CAP:
                break
            kept.append(entry)
        self.hot_path.write_text("\n".join(header + kept) + "\n", encoding="utf-8")

    # -- read ----------------------------------------------------------------

    def hot(self) -> str:
        return self.hot_path.read_text(encoding="utf-8")

    def recall(self, query: str, limit: int = 5) -> list[dict]:
        """Two-tier recall: score every memory by token overlap (title weighted 3x)."""
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        hits = []
        for path in self.memories_dir.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            title_match = re.search(r"^title:\s*(.+)$", text, re.MULTILINE)
            title = title_match.group(1).strip() if title_match else path.stem
            if title.startswith('"'):  # quoted frontmatter scalar
                try:
                    title = json.loads(title)
                except ValueError:
                    pass
            score = 3 * len(query_tokens & _tokens(title)) + len(query_tokens & _tokens(text))
            if score > 0:
                body = text.split("---", 2)[-1].strip()
                excerpt = re.sub(r"\s+", " ", body)[:200]
                hits.append({"slug": path.stem, "title": title, "score": score, "excerpt": excerpt})
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:limit]

    def stats(self) -> dict:
        return {
            "memories": len(list(self.memories_dir.glob("*.md"))),
            "hot_words": len(self.hot().split()),
        }
