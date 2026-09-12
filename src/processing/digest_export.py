"""Optional structured export of the items selected for a daily digest.

Writes a machine-readable JSON snapshot alongside the Markdown summaries so
downstream consumers (for example a Tolaria vault sync) do not have to parse
rendered Markdown. Export failures are non-fatal: the daily run must still
succeed when, for example, the data directory is read-only.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..models import ContentItem

logger = logging.getLogger(__name__)


def _iso(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _serialize_block(block: Any) -> Dict[str, Any]:
    return {
        "id": block.id,
        "title": block.title,
        "content": block.content,
        "primary": block.primary,
        "source_refs": list(block.source_refs),
    }


def _serialize_artifact(language: str, artifact: Any) -> Dict[str, Any]:
    return {
        "language": language,
        "title": artifact.title,
        "blocks": [_serialize_block(b) for b in artifact.blocks],
        "sources": [
            {"id": s.id, "title": s.title, "url": s.url} for s in artifact.sources
        ],
    }


def serialize_item(item: ContentItem) -> Dict[str, Any]:
    """Convert an enriched ContentItem into a JSON-safe dict."""
    processing = item.processing
    analysis = processing.analysis if processing else None
    classification = processing.classification if processing else None

    return {
        "id": item.id,
        "source_type": item.source_type.value,
        "title": item.title,
        "url": str(item.url),
        "author": item.author,
        "published_at": _iso(item.published_at),
        "profile": item.profile,
        "score": getattr(analysis, "score", None) if analysis else None,
        "summary": getattr(analysis, "summary", None) if analysis else None,
        "reason": getattr(analysis, "reason", None) if analysis else None,
        "tags": list(getattr(analysis, "tags", []) or []) if analysis else [],
        "category": getattr(classification, "category", None) if classification else None,
        "artifacts": {
            lang: _serialize_artifact(lang, artifact)
            for lang, artifact in (processing.artifacts.items() if processing else [])
        },
        "metadata": item.metadata,
    }


def build_export(
    *,
    date: str,
    items: List[ContentItem],
    total_fetched: int,
    languages: List[str],
) -> Dict[str, Any]:
    """Build the full export payload for one daily run."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date": date,
        "total_fetched": total_fetched,
        "selected_count": len(items),
        "languages": list(languages),
        "items": [serialize_item(item) for item in items],
    }


def write_export(data_dir: str | Path, payload: Dict[str, Any], date: str) -> Path:
    """Write the export to <data_dir>/items/<date>.json and return the path."""
    items_dir = Path(data_dir) / "items"
    items_dir.mkdir(parents=True, exist_ok=True)
    path = items_dir / f"{date}.json"
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)
    return path
