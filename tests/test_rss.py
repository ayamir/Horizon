from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from unittest.mock import MagicMock

from src.models import RSSSourceConfig
from src.scrapers.rss import RSSScraper

_FEED = """<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>Test</title>
  <item>
    <guid>entry-1</guid>
    <title>Item 1</title>
    <link>https://example.com/item-1</link>
    <pubDate>Fri, 24 Apr 2026 12:00:00 GMT</pubDate>
    <description>Short summary from feed.</description>
  </item>
</channel></rss>
"""
_SINCE = datetime(2026, 4, 24, 0, 0, tzinfo=timezone.utc)


def _make_feed_client(feed_text: str) -> AsyncMock:
    response = MagicMock()
    response.text = feed_text
    response.raise_for_status.return_value = None
    client = AsyncMock()
    client.get.return_value = response
    return client


def test_rss_ids_are_deterministic() -> None:
    client = _make_feed_client(_FEED)
    source = RSSSourceConfig(
        name="Test", url="https://example.com/feed.xml", profile="rss-profile"
    )
    scraper = RSSScraper([source], client)

    first_item = asyncio.run(scraper.fetch(_SINCE))[0]
    first = first_item.id
    second = asyncio.run(scraper.fetch(_SINCE))[0].id

    assert first == second
    assert first == "rss:example.com_feed.xml:5e2d5d1e58e94d76"
    assert first_item.profile == "rss-profile"


def test_timezone_less_pubdate_is_treated_as_utc() -> None:
    client = _make_feed_client(_FEED.replace(" GMT", ""))
    source = RSSSourceConfig(name="Test", url="https://example.com/feed.xml")
    scraper = RSSScraper([source], client)

    items = asyncio.run(scraper.fetch(_SINCE))

    assert len(items) == 1
    assert items[0].published_at == datetime(
        2026, 4, 24, 12, 0, tzinfo=timezone.utc
    )


def _make_registry(name: str, extractor):
    registry = MagicMock()
    registry.get.side_effect = lambda n: extractor if n == name else None
    return registry


def test_content_extractor_replaces_feed_content() -> None:
    client = _make_feed_client(_FEED)
    extractor = AsyncMock()
    extractor.extract.return_value = "Full article text from extractor."

    source = RSSSourceConfig(
        name="Test", url="https://example.com/feed.xml", content_extractor="my-ext"
    )
    scraper = RSSScraper([source], client, extractors=_make_registry("my-ext", extractor))
    items = asyncio.run(scraper.fetch(_SINCE))

    assert len(items) == 1
    assert items[0].content == "Full article text from extractor."
    extractor.extract.assert_awaited_once_with("https://example.com/item-1", client)


def test_content_extractor_falls_back_on_none() -> None:
    client = _make_feed_client(_FEED)
    extractor = AsyncMock()
    extractor.extract.return_value = None  # extraction failed

    source = RSSSourceConfig(
        name="Test", url="https://example.com/feed.xml", content_extractor="my-ext"
    )
    scraper = RSSScraper([source], client, extractors=_make_registry("my-ext", extractor))
    items = asyncio.run(scraper.fetch(_SINCE))

    assert len(items) == 1
    assert items[0].content == "Short summary from feed."


def test_unknown_extractor_name_ignored() -> None:
    client = _make_feed_client(_FEED)
    source = RSSSourceConfig(
        name="Test", url="https://example.com/feed.xml", content_extractor="nonexistent"
    )
    scraper = RSSScraper([source], client, extractors=_make_registry("other", AsyncMock()))
    items = asyncio.run(scraper.fetch(_SINCE))

    assert len(items) == 1
    assert items[0].content == "Short summary from feed."


# --- Per-source lookback override ---

def _old_feed(days_ago: int) -> str:
    """Feed with one entry published `days_ago` days before now.

    Built relative to the current time because the per-source override is
    resolved against `now`, not against the caller's `since`.
    """
    published = datetime.now(timezone.utc) - timedelta(days=days_ago)
    stamp = published.strftime("%a, %d %b %Y %H:%M:%S GMT")
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>Weekly</title>
  <item>
    <guid>old-1</guid>
    <title>Weekly post</title>
    <link>https://example.com/weekly-1</link>
    <pubDate>{stamp}</pubDate>
    <description>Published weeks ago.</description>
  </item>
</channel></rss>
"""


def _fetch(source: RSSSourceConfig, since: datetime, days_ago: int = 21):
    client = _make_feed_client(_old_feed(days_ago))
    scraper = RSSScraper([source], client)
    return asyncio.run(scraper._fetch_feed(source, since))


def test_old_entry_is_dropped_without_override() -> None:
    """Without an override, an entry outside the global window is skipped."""
    source = RSSSourceConfig(name="Weekly", url="https://example.com/rss")
    since = datetime.now(timezone.utc) - timedelta(hours=24)

    assert _fetch(source, since, days_ago=21) == []


def test_max_age_hours_admits_older_entries() -> None:
    """A wider per-source window lets slow-cadence feeds through.

    Uses the same `since` as the excluded case so the override is the only
    difference: without it the 21-day-old entry is filtered out.
    """
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    source = RSSSourceConfig(
        name="Weekly",
        url="https://example.com/rss",
        max_age_hours=24 * 60,
    )

    items = _fetch(source, since, days_ago=21)

    assert [i.title for i in items] == ["Weekly post"]


def test_narrower_override_does_not_widen_the_global_window() -> None:
    """The override never narrows the caller's window."""
    source = RSSSourceConfig(
        name="Weekly",
        url="https://example.com/rss",
        max_age_hours=1,
    )
    days_ago = 21
    recent_since = datetime.now(timezone.utc) - timedelta(days=30)

    items = _fetch(source, recent_since, days_ago=days_ago)

    assert [i.title for i in items] == ["Weekly post"]


# --- Per-source item cap ---

def _multi_item_feed(count: int) -> str:
    now = datetime.now(timezone.utc)
    entries = "".join(
        f"""  <item>
    <guid>entry-{i}</guid>
    <title>Item {i}</title>
    <link>https://example.com/item-{i}</link>
    <pubDate>{(now - timedelta(hours=i)).strftime("%a, %d %b %Y %H:%M:%S GMT")}</pubDate>
    <description>Body {i}.</description>
  </item>
"""
        for i in range(count)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"><channel><title>Many</title>
{entries}</channel></rss>
"""


def test_fetch_limit_caps_returned_items() -> None:
    """A wide window on a backlog-heavy feed must not flood the run."""
    source = RSSSourceConfig(
        name="Many",
        url="https://example.com/rss",
        max_age_hours=24 * 60,
        fetch_limit=3,
    )
    scraper = RSSScraper([source], _make_feed_client(_multi_item_feed(10)))

    items = asyncio.run(
        scraper._fetch_feed(source, datetime.now(timezone.utc) - timedelta(hours=1))
    )

    assert len(items) == 3


def test_fetch_limit_keeps_the_newest_items() -> None:
    """The cap keeps the first (newest) entries, not an arbitrary slice."""
    source = RSSSourceConfig(
        name="Many",
        url="https://example.com/rss",
        max_age_hours=24 * 60,
        fetch_limit=2,
    )
    scraper = RSSScraper([source], _make_feed_client(_multi_item_feed(10)))

    items = asyncio.run(
        scraper._fetch_feed(source, datetime.now(timezone.utc) - timedelta(hours=1))
    )

    assert [i.title for i in items] == ["Item 0", "Item 1"]


def test_without_fetch_limit_all_items_are_returned() -> None:
    source = RSSSourceConfig(
        name="Many",
        url="https://example.com/rss",
        max_age_hours=24 * 60,
    )
    scraper = RSSScraper([source], _make_feed_client(_multi_item_feed(10)))

    items = asyncio.run(
        scraper._fetch_feed(source, datetime.now(timezone.utc) - timedelta(hours=1))
    )

    assert len(items) == 10
