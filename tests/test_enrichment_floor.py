"""Tests for the enrichment score floor.

Enrichment is the expensive second AI pass. Quota groups deliberately admit
some low-scoring items to keep their tier populated, so this floor lets those
items stay in the digest while skipping the extra API calls.
"""

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from rich.console import Console

from src.ai.enricher import EnrichmentBatchResult
from src.models import (
    ClassificationResult,
    ContentAnalysis,
    ContentItem,
    DigestConfig,
    ProcessingConfig,
    ProcessingResult,
    SourceType,
)
from src.orchestrator import HorizonOrchestrator, _item_score


def make_item(item_id: str, score: float) -> ContentItem:
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


def make_orchestrator(min_score: float | None) -> HorizonOrchestrator:
    orchestrator = HorizonOrchestrator.__new__(HorizonOrchestrator)
    orchestrator.config = SimpleNamespace(
        digest=DigestConfig(enrichment_min_score=min_score),
        processing=ProcessingConfig(profile_settings={}),
        ai=SimpleNamespace(languages=["zh"]),
    )
    orchestrator.profiles = SimpleNamespace()
    orchestrator.console = Console(record=True)
    return orchestrator


def _capture_enriched(monkeypatch, orchestrator, sink: list[list[ContentItem]]):
    """Replace the batch enricher so no AI client is constructed."""

    class FakeEnricher:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def enrich_batch(self, items: list[ContentItem]):
            sink.append(list(items))
            return EnrichmentBatchResult(succeeded_ids=[i.id for i in items])

    monkeypatch.setattr("src.orchestrator.create_ai_client", lambda *a, **k: None)
    monkeypatch.setattr("src.orchestrator.ContentEnricher", FakeEnricher)


def test_item_score_reads_analysis_score() -> None:
    assert _item_score(make_item("a", 7.5)) == 7.5


def test_item_score_is_negative_without_analysis() -> None:
    item = ContentItem(
        id="raw",
        source_type=SourceType.RSS,
        title="raw",
        url="https://example.com/raw",
        published_at=datetime.now(timezone.utc),
    )

    assert _item_score(item) == -1.0


def test_low_scoring_items_are_not_enriched(monkeypatch) -> None:
    orchestrator = make_orchestrator(min_score=6.0)
    sent: list[list[ContentItem]] = []
    _capture_enriched(monkeypatch, orchestrator, sent)

    items = [make_item("high", 8.0), make_item("low", 4.0)]

    asyncio.run(orchestrator.enrich_items(items))

    assert [i.id for batch in sent for i in batch] == ["high"]


def test_floor_keeps_low_items_in_the_digest(monkeypatch) -> None:
    """Skipping enrichment must not drop the item from the caller's list."""
    orchestrator = make_orchestrator(min_score=6.0)
    sent: list[list[ContentItem]] = []
    _capture_enriched(monkeypatch, orchestrator, sent)

    items = [make_item("high", 8.0), make_item("low", 4.0)]

    asyncio.run(orchestrator.enrich_items(items))

    assert len(items) == 2


def test_no_floor_enriches_everything(monkeypatch) -> None:
    orchestrator = make_orchestrator(min_score=None)
    sent: list[list[ContentItem]] = []
    _capture_enriched(monkeypatch, orchestrator, sent)

    asyncio.run(orchestrator.enrich_items([make_item("a", 4.0), make_item("b", 8.0)]))

    assert sorted(i.id for batch in sent for i in batch) == ["a", "b"]


def test_all_items_below_floor_skips_the_batch(monkeypatch) -> None:
    orchestrator = make_orchestrator(min_score=6.0)
    sent: list[list[ContentItem]] = []
    _capture_enriched(monkeypatch, orchestrator, sent)

    asyncio.run(orchestrator.enrich_items([make_item("low", 3.0)]))

    assert sent == []


def test_empty_input_returns_early() -> None:
    orchestrator = make_orchestrator(min_score=6.0)

    result = asyncio.run(orchestrator.enrich_items([]))

    assert result.succeeded_count == 0
