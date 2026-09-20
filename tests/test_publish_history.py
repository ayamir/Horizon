"""Tests for cross-day publish deduplication.

Feeds serve a rolling window, and the per-source `max_age_hours` that weekly
publishers need keeps their entries eligible for days. Without a record of
what already shipped, the same story reappears and consumes a quota slot that
fresh material could have used.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from src.models import (
    ClassificationResult,
    ContentAnalysis,
    ContentItem,
    DigestConfig,
    ProcessingConfig,
    ProcessingResult,
    SourceType,
)
from src.orchestrator import HorizonOrchestrator
from src.storage.manager import StorageManager


def make_item(item_id: str, score: float = 8.0) -> ContentItem:
    return ContentItem(
        id=item_id,
        source_type=SourceType.RSS,
        title=item_id,
        url=f"https://example.com/{item_id}",
        published_at=datetime.now(timezone.utc),
        profile="tech-news",
        processing=ProcessingResult(
            classification=ClassificationResult(
                profile="tech-news", method="source_override"
            ),
            analysis=ContentAnalysis(score=score, reason="test", summary=item_id),
        ),
    )


def make_orchestrator(tmp_path: Path) -> HorizonOrchestrator:
    orchestrator = HorizonOrchestrator.__new__(HorizonOrchestrator)
    orchestrator.config = SimpleNamespace(
        digest=DigestConfig(),
        processing=ProcessingConfig(profile_settings={}),
    )
    orchestrator.console = Console(record=True)
    orchestrator.storage = StorageManager(data_dir=str(tmp_path))
    return orchestrator


def test_missing_index_keeps_everything(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    items = [make_item("a"), make_item("b")]

    assert orchestrator._drop_already_published(items) == items


def test_previously_published_items_are_dropped(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    orchestrator.storage.save_published_index({"old": "2026-09-15"})

    kept = orchestrator._drop_already_published([make_item("old"), make_item("new")])

    assert [i.id for i in kept] == ["new"]


def test_recording_marks_items_with_the_run_date(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)

    orchestrator._record_published([make_item("a"), make_item("b")], "2026-09-21")

    index = orchestrator.storage.load_published_index()
    assert index == {"a": "2026-09-21", "b": "2026-09-21"}


def test_recording_preserves_the_earliest_date(tmp_path: Path) -> None:
    """A story keeps its first publication date if it is recorded twice."""
    orchestrator = make_orchestrator(tmp_path)
    orchestrator.storage.save_published_index({"a": "2026-09-15"})

    orchestrator._record_published([make_item("a")], "2026-09-21")

    assert orchestrator.storage.load_published_index() == {"a": "2026-09-15"}


def test_round_trip_drops_a_story_on_the_second_day(tmp_path: Path) -> None:
    """The full cycle: publish, then confirm it is filtered out next run."""
    orchestrator = make_orchestrator(tmp_path)
    items = [make_item("story")]

    orchestrator._record_published(items, "2026-09-20")
    kept = orchestrator._drop_already_published([make_item("story")])

    assert kept == []


def test_corrupt_index_is_treated_as_empty(tmp_path: Path) -> None:
    """A damaged index must not block publishing."""
    orchestrator = make_orchestrator(tmp_path)
    orchestrator.storage.published_index_path.write_text("{ not json", encoding="utf-8")

    assert orchestrator.storage.load_published_index() == {}


def test_index_survives_a_unicode_round_trip(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)
    orchestrator.storage.save_published_index({"rss:例子:1": "2026-09-21"})

    assert orchestrator.storage.load_published_index() == {"rss:例子:1": "2026-09-21"}


def test_empty_input_returns_early(tmp_path: Path) -> None:
    orchestrator = make_orchestrator(tmp_path)

    assert orchestrator._drop_already_published([]) == []
    # Recording nothing must not create a file.
    orchestrator._record_published([], "2026-09-21")
    assert not orchestrator.storage.published_index_path.exists()
