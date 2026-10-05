"""Settings from the environment and from ``.env`` in the working directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from us_places_mcp.config import (
    DEFAULT_OVERPASS_URL,
    DEFAULT_PLSS_URL,
    ConfigError,
    load_config,
)

VARIABLES = (
    "US_PLACES_OVERPASS_URL",
    "US_PLACES_PLSS_URL",
    "US_PLACES_CACHE_DIR",
    "US_PLACES_TIMEOUT",
    "US_PLACES_CONTACT",
)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_nothing_is_required():
    cfg = load_config()
    assert (cfg.overpass_url, cfg.plss_url) == (DEFAULT_OVERPASS_URL, DEFAULT_PLSS_URL)
    assert cfg.timeout == 60.0 and cfg.contact == ""
    assert cfg.cache_dir == Path.home() / ".cache" / "us-places-mcp"


def test_every_setting_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("US_PLACES_OVERPASS_URL", "https://overpass.example.org/api/interpreter")
    monkeypatch.setenv("US_PLACES_PLSS_URL", "https://gis.example.gov/MapServer/")
    monkeypatch.setenv("US_PLACES_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("US_PLACES_TIMEOUT", "15")
    monkeypatch.setenv("US_PLACES_CONTACT", "me@example.org")
    cfg = load_config()
    assert cfg.overpass_url == "https://overpass.example.org/api/interpreter"
    assert cfg.plss_url == "https://gis.example.gov/MapServer"
    assert cfg.cache_dir == tmp_path / "c"
    assert (cfg.timeout, cfg.contact) == (15.0, "me@example.org")


@pytest.mark.parametrize("name", ["US_PLACES_OVERPASS_URL", "US_PLACES_PLSS_URL"])
@pytest.mark.parametrize("url", ["http://example.org/x", "example.org", "https://"])
def test_service_urls_must_be_https_with_a_host(monkeypatch, name, url):
    monkeypatch.setenv(name, url)
    with pytest.raises(ConfigError, match=name):
        load_config()


@pytest.mark.parametrize("raw", ["sixty", "0", "-5", "nan", "inf"])
def test_an_unusable_timeout_names_the_variable(monkeypatch, raw):
    monkeypatch.setenv("US_PLACES_TIMEOUT", raw)
    with pytest.raises(ConfigError, match="US_PLACES_TIMEOUT"):
        load_config()


@pytest.mark.parametrize("raw", ["me@example.org\r\nX-Evil: 1", "me (home)"])
def test_a_contact_that_could_break_the_header_is_refused(monkeypatch, raw):
    monkeypatch.setenv("US_PLACES_CONTACT", raw)
    with pytest.raises(ConfigError, match="US_PLACES_CONTACT"):
        load_config()


def test_dot_env_in_the_working_directory_is_read(tmp_path):
    (tmp_path / ".env").write_text("US_PLACES_TIMEOUT=7\n")
    assert load_config().timeout == 7.0
