"""Tests for the GitHub scraper's credential handling."""

import httpx
import pytest

from src.models import GitHubSourceConfig
from src.scrapers.github import GitHubScraper


def _scraper() -> GitHubScraper:
    sources = [
        GitHubSourceConfig(
            type="repo_releases",
            owner="astral-sh",
            repo="uv",
            enabled=True,
            profile="tech-news",
            category="ai-tools",
        )
    ]
    return GitHubScraper(sources, httpx.AsyncClient())


def test_placeholder_token_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    """The `.env.example` stub must not be sent as credentials.

    Sending `ghp_xxx` makes every request fail with 401, while the same
    request without an Authorization header succeeds anonymously.
    """
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxx")

    headers = _scraper()._get_headers()

    assert "Authorization" not in headers


def test_blank_token_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "   ")

    headers = _scraper()._get_headers()

    assert "Authorization" not in headers


def test_missing_token_is_not_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    headers = _scraper()._get_headers()

    assert "Authorization" not in headers


def test_real_token_is_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    token = "ghp_" + "a" * 36
    monkeypatch.setenv("GITHUB_TOKEN", token)

    headers = _scraper()._get_headers()

    assert headers["Authorization"] == f"token {token}"


def test_headers_always_include_accept_and_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    headers = _scraper()._get_headers()

    assert headers["Accept"] == "application/vnd.github.v3+json"
    assert headers["User-Agent"] == "Horizon-Aggregator"
