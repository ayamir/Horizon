#!/usr/bin/env python3
"""Sync a Horizon daily digest into the Tolaria vault as one `news` note.

Reads the structured export written by Horizon at <data_dir>/items/<date>.json
and writes a single Markdown note per day containing every selected item plus a
table of contents. Safe to re-run: the note is located by `horizon_id` in
frontmatter, so a re-run overwrites it in place instead of duplicating it.

Usage:
    python scripts/sync_to_tolaria.py --date 2026-09-12
    python scripts/sync_to_tolaria.py --latest
    python scripts/sync_to_tolaria.py --latest --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_VAULT = Path.home() / "Documents" / "Tolaria"
NEWS_TYPE = "news"
# Preferred artifact order for the note body. The vault notes are written in
# Chinese, so ask for `zh` first and fall back to whatever exists.
DISPLAY_LANGUAGES = ["zh", "en"]

# Profile slug -> section heading shown in the note.
PROFILE_LABELS = {
    "tech-news": "科技新闻",
    "tech-blog": "科技博客",
    "finance-news": "财经新闻",
    "news": "新闻",
}
PROFILE_ORDER = ["tech-news", "tech-blog", "finance-news", "news"]


def _display_time(value: Any) -> str:
    """Render an ISO timestamp as a compact local date and time."""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return text
    return parsed.astimezone().strftime("%Y-%m-%d %H:%M")


def normalize_profile(value: Any) -> str:
    """Collapse a profile value into one section slug.

    Telegram channels can route to several profiles, so ``profile`` may be a
    list. Pick the first entry and keep the section stable.
    """
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    text = str(value).strip() if value is not None else ""
    return text or "news"


def yaml_quote(value: str) -> str:
    """Quote a scalar for YAML, escaping quotes and collapsing newlines."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", " ").strip()
    return f'"{escaped}"'


def build_frontmatter(payload: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    """Compose Tolaria frontmatter for the daily digest note."""
    date = payload["date"]
    tags = ["horizon", NEWS_TYPE]
    for item in items:
        for tag in item.get("tags") or []:
            cleaned = re.sub(r"[^\w\-]", "-", str(tag)).strip("-").lower()
            if cleaned and cleaned not in tags:
                tags.append(cleaned)

    lines = [
        "---",
        f'title: "Horizon 每日速递 {date}"',
        f"type: {NEWS_TYPE}",
        f"horizon_id: {yaml_quote(f'digest:{date}')}",
        f"date: {date}",
        f"source: {yaml_quote('horizon')}",
        f"selected_count: {len(items)}",
        f"total_fetched: {payload.get('total_fetched') or 0}",
    ]
    profiles = sorted(
        {normalize_profile(i.get("profile")) for i in items},
        key=lambda p: PROFILE_ORDER.index(p) if p in PROFILE_ORDER else 99,
    )
    lines.append("profiles:")
    for profile in profiles:
        lines.append(f"  - {yaml_quote(profile)}")

    lines.append("tags:")
    for tag in tags:
        lines.append(f"  - {yaml_quote(tag)}")
    lines.append("---")
    return "\n".join(lines)


def _artifact_for(item: Dict[str, Any], languages: List[str]) -> Optional[Dict[str, Any]]:
    """Pick the preferred-language artifact, falling back to any available."""
    artifacts = item.get("artifacts") or {}
    for lang in languages:
        if lang in artifacts:
            return artifacts[lang]
    for artifact in artifacts.values():
        return artifact
    return None


def display_title(item: Dict[str, Any], artifact: Optional[Dict[str, Any]]) -> str:
    """Prefer the localized artifact title over the source's own title."""
    if artifact and artifact.get("title"):
        return str(artifact["title"])
    return str(item["title"])


def display_summary(item: Dict[str, Any], artifact: Optional[Dict[str, Any]]) -> str:
    """Use the localized summary block when present."""
    if artifact:
        for block in artifact.get("blocks") or []:
            if block.get("primary") and block.get("content"):
                return str(block["content"])
    return str(item.get("summary") or "")


def _grouped(items: List[Dict[str, Any]]) -> List[Tuple[str, List[Tuple[int, Dict[str, Any]]]]]:
    """Bucket items by profile, renumbering each bucket from 1.

    Profile sections are rendered independently, so a global running number
    would jump (e.g. section two starting at 9) and read like a missing item.
    """
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        grouped.setdefault(normalize_profile(item.get("profile")), []).append(item)
    return [
        (profile, list(enumerate(bucket, start=1)))
        for profile, bucket in sorted(
            grouped.items(),
            key=lambda kv: PROFILE_ORDER.index(kv[0]) if kv[0] in PROFILE_ORDER else 99,
        )
    ]


def build_toc(items: List[Dict[str, Any]], languages: List[str]) -> str:
    """Render a plain table of contents grouped by profile.

    Tolaria resolves wikilinks between notes but not anchors inside a note, so
    a linked TOC here would be markup that looks interactive and does nothing.
    Keep it as a scannable index and let the reader use search to jump.
    """
    lines: List[str] = []
    for profile, entries in _grouped(items):
        lines.append(f"**{PROFILE_LABELS.get(profile, profile)}**")
        lines.append("")
        for idx, item in entries:
            artifact = _artifact_for(item, languages)
            score = item.get("score")
            suffix = f" — ⭐️ {score}/10" if score is not None else ""
            lines.append(f"{idx}. {display_title(item, artifact)}{suffix}")
        lines.append("")
    return "\n".join(lines).strip()


def build_item_section(item: Dict[str, Any], idx: int, languages: List[str]) -> str:
    """Render one digest entry."""
    parts: List[str] = []
    score = item.get("score")
    artifact = _artifact_for(item, languages)

    title = display_title(item, artifact)
    parts.append(
        f'### {idx}. [{title}]({item["url"]})'
        + (f" — ⭐️ {score}/10" if score is not None else "")
    )

    profile = normalize_profile(item.get("profile"))
    meta_bits = [f"`{item['source_type']}`"]
    if item.get("author"):
        meta_bits.append(str(item["author"]))
    if item.get("published_at"):
        meta_bits.append(_display_time(item["published_at"]))
    meta_bits.append(PROFILE_LABELS.get(profile, profile))
    parts.append(" · ".join(meta_bits))

    summary = display_summary(item, artifact)
    if summary:
        parts.append(summary)

    if artifact:
        for block in artifact.get("blocks") or []:
            if block.get("primary"):
                # Already emitted above as the localized summary.
                continue
            title = block.get("title")
            content = block.get("content")
            if not content:
                continue
            parts.append(f"**「{title}」** {content}" if title else str(content))

    sources = (artifact or {}).get("sources") or []
    if sources:
        links = "\n".join(
            f"- [{s.get('title') or s.get('url')}]({s.get('url')})" for s in sources
        )
        parts.append(f"**参考链接**\n{links}")

    tags = item.get("tags") or []
    if tags:
        parts.append("**标签**: " + ", ".join(f"`#{t}`" for t in tags))

    return "\n\n".join(parts)


def build_body(payload: Dict[str, Any], items: List[Dict[str, Any]]) -> str:
    """Compose the full note: intro, TOC, then every entry."""
    date = payload["date"]
    # Always render the note in the preferred language rather than trusting the
    # pipeline's own language order, which lists `en` first.
    languages = DISPLAY_LANGUAGES + [
        lang for lang in (payload.get("languages") or []) if lang not in DISPLAY_LANGUAGES
    ]
    total = payload.get("total_fetched") or 0

    parts: List[str] = []
    parts.append(
        f"> 从 {total} 条内容中筛选出 {len(items)} 条重要资讯。"
        if total
        else f"> 本日筛选出 {len(items)} 条重要资讯。"
    )
    parts.append("## 目录\n\n" + build_toc(items, languages))

    for profile, entries in _grouped(items):
        parts.append(f"## {PROFILE_LABELS.get(profile, profile)}")
        for idx, item in entries:
            parts.append(build_item_section(item, idx, languages))

    return "\n\n".join(parts) + "\n"


def index_existing(vault: Path) -> Dict[str, Path]:
    """Map horizon_id -> note path for every note already synced."""
    index: Dict[str, Path] = {}
    pattern = re.compile(r'^horizon_id:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
    for path in vault.rglob("*.md"):
        if ".git" in path.parts:
            continue
        try:
            head = path.read_text(encoding="utf-8")[:2000]
        except (OSError, UnicodeDecodeError):
            continue
        match = pattern.search(head)
        if match:
            index[match.group(1).strip()] = path
    return index


def resolve_export(data_dir: Path, date: Optional[str], latest: bool) -> Path:
    items_dir = data_dir / "items"
    if latest:
        candidates = sorted(items_dir.glob("*.json"))
        if not candidates:
            raise SystemExit(f"error: no exports found in {items_dir}")
        return candidates[-1]
    if not date:
        raise SystemExit("error: pass --date YYYY-MM-DD or --latest")
    path = items_dir / f"{date}.json"
    if not path.exists():
        raise SystemExit(f"error: export not found: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="digest date, e.g. 2026-09-12")
    parser.add_argument("--latest", action="store_true", help="use newest export")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="vault root")
    parser.add_argument("--data-dir", default="data", help="Horizon data directory")
    parser.add_argument(
        "--subdir",
        default="news",
        help="folder inside the vault for synced notes ('' to write at root)",
    )
    parser.add_argument("--dry-run", action="store_true", help="print, do not write")
    args = parser.parse_args()

    vault = Path(args.vault).expanduser()
    if not vault.is_dir():
        raise SystemExit(f"error: vault not found: {vault}")

    export_path = resolve_export(Path(args.data_dir), args.date, args.latest)
    payload = json.loads(export_path.read_text(encoding="utf-8"))

    date = payload["date"]
    items: List[Dict[str, Any]] = payload.get("items") or []
    if not items:
        print(f"Nothing to sync: {export_path.name} has no items", file=sys.stderr)
        return 0

    target_dir = vault / args.subdir if args.subdir else vault
    note_id = f"digest:{date}"
    filename = f"{date}-horizon-daily.md"

    existing = index_existing(vault)
    path = existing.get(note_id) or (target_dir / filename)

    content = build_frontmatter(payload, items) + "\n\n" + build_body(payload, items)

    if args.dry_run:
        print(f"--- {path.relative_to(vault)} ---")
        print(content)
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    path.write_text(content, encoding="utf-8")

    action = "Updated" if existed else "Created"
    print(
        f"{action} {path} "
        f"({len(items)} item(s) from {export_path.name})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
