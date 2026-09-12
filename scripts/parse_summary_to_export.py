#!/usr/bin/env python3
"""Convert an existing Horizon Markdown summary into the JSON export format.

Lets you sync a digest that was produced before the structured export existed,
without re-running the (paid) AI pipeline.

Usage:
    python scripts/parse_summary_to_export.py data/summaries/horizon-2026-09-12-zh.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

SECTION_RE = re.compile(r"^## (.+?)\s*$", re.MULTILINE)
ITEM_RE = re.compile(r'<a id="(item-[^"]+)"></a>\s*\n### \[(.+?)\]\((\S+?)\)(?:\s*⭐️\s*([\d.]+)/10)?\s*$', re.MULTILINE)


def strip_html(text: str) -> str:
    text = re.sub(r"</?(?:ul|li|details|summary|p|div|br)\s*/?>", "", text)
    return text.strip()


def parse_sources(chunk: str) -> List[Dict[str, str]]:
    """Extract reference links from the <details> block."""
    block = re.search(r"<details>.*?</details>", chunk, re.DOTALL)
    if not block:
        return []
    sources = []
    for href, label in re.findall(r'<a href="([^"]+)">(.*?)</a>', block.group(0)):
        sources.append({"id": href, "title": strip_html(label), "url": href})
    return sources


SECTION_TO_PROFILE = {
    "科技新闻": "tech-news",
    "科技博客": "tech-blog",
    "财经新闻": "finance-news",
    "新闻": "news",
}


def parse_items(markdown: str, date: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    # Build a section map so each item knows its profile/category.
    section_positions = [(m.start(), m.group(1).strip()) for m in SECTION_RE.finditer(markdown)]

    def section_for(pos: int) -> str:
        current = "news"
        for start, name in section_positions:
            if start <= pos:
                current = name
            else:
                break
        return current

    matches = list(ITEM_RE.finditer(markdown))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(markdown)
        chunk = markdown[start:end]

        anchor, title, url, score = match.groups()
        section = section_for(start)
        profile = SECTION_TO_PROFILE.get(section, "news")
        sources = parse_sources(chunk)

        # Enrichment blocks look like: **「背景」** <content>
        body = re.sub(r"<details>.*?</details>", "", chunk, flags=re.DOTALL)
        blocks = []
        for bm in re.finditer(r"\*\*「(.+?)」\*\*\s*(.+?)(?=\n\s*\n|\Z)", body, re.DOTALL):
            blocks.append(
                {
                    "id": f"block-{len(blocks) + 1}",
                    "title": bm.group(1).strip(),
                    "content": bm.group(2).strip(),
                    "primary": len(blocks) == 0,
                    "source_refs": [],
                }
            )

        # The first paragraph after the heading is the summary.
        after_heading = body[match.end() - start :]
        summary = ""
        for para in re.split(r"\n\s*\n", after_heading):
            para = para.strip()
            if not para or para.startswith("**「") or para.startswith("**标签**"):
                continue
            if "·" in para and ("[社区讨论]" in para or len(para) < 160):
                break
            summary = para
            break

        tags: List[str] = []
        tag_match = re.search(r"\*\*标签\*\*:\s*(.+)", body)
        if tag_match:
            tags = [
                t.strip().lstrip("#")
                for t in re.findall(r"`#([^`]+)`", tag_match.group(1))
            ]

        # Source metadata line, e.g. "hackernews · zdw · 9月12日 07:54"
        source_type = "rss"
        author = None
        published = None
        for line in body.splitlines():
            line = line.strip()
            if "·" in line and not line.startswith(("#", "*", "-", "<", "[")):
                bits = [b.strip() for b in line.split("·")]
                if bits:
                    source_type = bits[0]
                if len(bits) > 1 and not bits[1].startswith("["):
                    author = bits[1]
                if len(bits) > 2:
                    published = bits[2]
                break

        items.append(
            {
                "id": f"{source_type}:summary:{anchor}",
                "source_type": source_type,
                "title": title.strip(),
                "url": url.strip(),
                "author": author,
                "published_at": published,
                "profile": profile,
                "score": float(score) if score else None,
                "summary": summary,
                "reason": None,
                "tags": tags,
                "category": section,
                "artifacts": {
                    "zh": {
                        "language": "zh",
                        "title": title.strip(),
                        "blocks": blocks,
                        "sources": sources,
                    }
                },
                "metadata": {"anchor": anchor, "parsed_from": "markdown"},
            }
        )

    return items


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", help="path to horizon-<date>-<lang>.md")
    parser.add_argument("--data-dir", default="data", help="Horizon data directory")
    parser.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = parser.parse_args()

    path = Path(args.summary)
    if not path.exists():
        raise SystemExit(f"error: not found: {path}")

    match = re.match(r"horizon-(\d{4}-\d{2}-\d{2})-(\w+)\.md$", path.name)
    date, lang = (match.group(1), match.group(2)) if match else (
        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "zh",
    )

    markdown = path.read_text(encoding="utf-8")
    items = parse_items(markdown, date)

    total = 0
    total_match = re.search(r"从\s*(\d+)\s*条内容中筛选出|from\s*(\d+)\s*items", markdown)
    if total_match:
        total = int(total_match.group(1) or total_match.group(2))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": date,
        "total_fetched": total,
        "selected_count": len(items),
        "languages": [lang],
        "items": items,
        "metadata": {"parsed_from": str(path)},
    }

    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    out_dir = Path(args.data_dir) / "items"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Parsed {len(items)} item(s) from {path.name} → {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
