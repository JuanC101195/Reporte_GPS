"""Unit tests for src.maps_preview."""

from urllib.parse import parse_qs, urlparse

import pytest

from src import maps_preview
from src.maps_preview import (
    ENV_VAR,
    get_api_key,
    gmaps_link,
    preview_cell_html,
    preview_thumb_html,
    staticmap_url,
    streetview_url,
)


@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setenv(ENV_VAR, "fake-test-key-123")
    return "fake-test-key-123"


@pytest.fixture
def no_key(monkeypatch):
    monkeypatch.delenv(ENV_VAR, raising=False)


class TestGetApiKey:
    def test_reads_from_env(self, fake_key):
        assert get_api_key() == fake_key

    def test_returns_none_when_missing(self, no_key):
        assert get_api_key() is None

    def test_treats_blank_as_missing(self, monkeypatch):
        monkeypatch.setenv(ENV_VAR, "   ")
        assert get_api_key() is None


class TestStreetviewUrl:
    def test_returns_none_without_key(self, no_key):
        assert streetview_url(10.38, -75.47) is None

    def test_builds_url_with_key(self, fake_key):
        url = streetview_url(10.38, -75.47)
        parsed = urlparse(url)
        assert parsed.netloc == "maps.googleapis.com"
        assert parsed.path == "/maps/api/streetview"
        qs = parse_qs(parsed.query)
        assert qs["key"] == [fake_key]
        assert qs["location"] == ["10.380000,-75.470000"]
        assert "size" in qs

    def test_explicit_key_overrides_env(self, no_key):
        url = streetview_url(10.0, -75.0, api_key="explicit")
        assert url is not None
        assert "key=explicit" in url


class TestStaticmapUrl:
    def test_returns_none_without_key(self, no_key):
        assert staticmap_url(10.38, -75.47) is None

    def test_includes_marker_and_maptype(self, fake_key):
        url = staticmap_url(10.38, -75.47)
        qs = parse_qs(urlparse(url).query)
        assert qs["maptype"] == ["hybrid"]
        assert qs["zoom"] == ["19"]
        assert any("10.380000,-75.470000" in m for m in qs["markers"])


class TestGmapsLink:
    def test_no_key_needed(self, no_key):
        link = gmaps_link(10.38, -75.47)
        assert link == "https://www.google.com/maps?q=10.380000,-75.470000"


class TestPreviewCellHtml:
    def test_none_coords_returns_dash(self, fake_key):
        assert preview_cell_html(None, None) == "-"
        assert preview_cell_html(10.0, None) == "-"

    def test_without_key_falls_back_to_text_link(self, no_key):
        html = preview_cell_html(10.38, -75.47)
        assert "Ver en Maps" in html
        assert "<img" not in html
        assert "google.com/maps" in html

    def test_with_key_embeds_two_thumbnails(self, fake_key):
        html = preview_cell_html(10.38, -75.47)
        # Two <img> tags, one Street View and one satellite
        assert html.count("<img") == 2
        assert "streetview" in html
        assert "staticmap" in html
        # Deep link always present
        assert "google.com/maps" in html

    def test_key_is_not_logged_or_leaked_as_plain_text(self, fake_key):
        html = preview_cell_html(10.38, -75.47)
        # The key does end up in the img src (that's expected for static APIs),
        # but we want to ensure it's only inside src="..." and not anywhere else.
        # Count occurrences: should equal number of authenticated URLs (2).
        assert html.count(fake_key) == 2


class TestPreviewThumbHtml:
    def test_none_coords_returns_dash(self, fake_key):
        assert preview_thumb_html(None, None) == "-"
        assert preview_thumb_html(10.0, None) == "-"

    def test_without_key_returns_dash(self, no_key):
        # No API key means no useful preview at all; thumb is decorative
        # only and there is no fallback text link (the parent card is
        # already clickable, no extra link needed here).
        assert preview_thumb_html(10.38, -75.47) == "-"

    def test_with_key_has_no_nested_anchors(self, fake_key):
        html = preview_thumb_html(10.38, -75.47)
        # 2 <img> tags, one per API
        assert html.count("<img") == 2
        assert "streetview" in html
        assert "staticmap" in html
        # CRITICAL: no <a> tags at all (this is the whole point —
        # these thumbs are rendered inside a parent <a>).
        assert "<a " not in html
        assert "</a>" not in html


class TestRendererIntegration:
    """Ensure the renderer module imports preview_cell_html successfully."""

    def test_renderer_import(self):
        from src import report_anomalias
        assert hasattr(report_anomalias, "generar_html_anomalias")
        # preview_cell_html is imported privately but the module must still load
        assert maps_preview.preview_cell_html is not None
