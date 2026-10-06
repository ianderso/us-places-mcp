"""Settings from the environment and from ``.env`` in the working directory."""

from __future__ import annotations

from pathlib import Path

import pytest

from us_places_mcp.config import (
    DEFAULT_DATAVERSE_URL,
    DEFAULT_GNIS_ARCHIVE_URL,
    DEFAULT_GNIS_URL,
    DEFAULT_OVERPASS_URL,
    DEFAULT_PLSS_URL,
    DEFAULT_TNM_URL,
    Config,
    ConfigError,
    load_config,
)

URL_VARIABLES = (
    "US_PLACES_OVERPASS_URL",
    "US_PLACES_PLSS_URL",
    "US_PLACES_GNIS_URL",
    "US_PLACES_GNIS_ARCHIVE_URL",
    "US_PLACES_TNM_URL",
    "US_PLACES_DATAVERSE_URL",
)
VARIABLES = (*URL_VARIABLES, "US_PLACES_CACHE_DIR", "US_PLACES_TIMEOUT", "US_PLACES_CONTACT")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)


def test_nothing_is_required():
    cfg = load_config()
    assert (cfg.overpass_url, cfg.plss_url) == (DEFAULT_OVERPASS_URL, DEFAULT_PLSS_URL)
    assert (cfg.gnis_url, cfg.gnis_archive_url) == (DEFAULT_GNIS_URL, DEFAULT_GNIS_ARCHIVE_URL)
    assert (cfg.tnm_url, cfg.dataverse_url) == (DEFAULT_TNM_URL, DEFAULT_DATAVERSE_URL)
    assert cfg.timeout == 60.0 and cfg.contact == ""
    assert cfg.cache_dir == Path.home() / ".cache" / "us-places-mcp"
    assert cfg.data_dir == cfg.cache_dir / "data"


def test_datasets_follow_the_cache_directory(monkeypatch, tmp_path):
    monkeypatch.setenv("US_PLACES_CACHE_DIR", str(tmp_path / "c"))
    assert load_config().data_dir == tmp_path / "c" / "data"
    assert Config(cache_dir=tmp_path, datasets_dir=tmp_path / "d").data_dir == tmp_path / "d"


def test_every_setting_is_read(monkeypatch, tmp_path):
    monkeypatch.setenv("US_PLACES_OVERPASS_URL", "https://overpass.example.org/api/interpreter")
    monkeypatch.setenv("US_PLACES_PLSS_URL", "https://gis.example.gov/MapServer/")
    monkeypatch.setenv("US_PLACES_GNIS_URL", "https://names.example.gov/MapServer/")
    monkeypatch.setenv("US_PLACES_GNIS_ARCHIVE_URL", "https://files.example.gov/gnis/")
    monkeypatch.setenv("US_PLACES_TNM_URL", "https://tnm.example.gov/api/v1/products")
    monkeypatch.setenv("US_PLACES_DATAVERSE_URL", "https://dataverse.example.edu/")
    monkeypatch.setenv("US_PLACES_CACHE_DIR", str(tmp_path / "c"))
    monkeypatch.setenv("US_PLACES_TIMEOUT", "15")
    monkeypatch.setenv("US_PLACES_CONTACT", "me@example.org")
    cfg = load_config()
    assert cfg.overpass_url == "https://overpass.example.org/api/interpreter"
    assert cfg.plss_url == "https://gis.example.gov/MapServer"
    assert cfg.gnis_url == "https://names.example.gov/MapServer"
    assert cfg.gnis_archive_url == "https://files.example.gov/gnis"
    assert cfg.tnm_url == "https://tnm.example.gov/api/v1/products"
    assert cfg.dataverse_url == "https://dataverse.example.edu"
    assert cfg.cache_dir == tmp_path / "c"
    assert (cfg.timeout, cfg.contact) == (15.0, "me@example.org")


@pytest.mark.parametrize("name", URL_VARIABLES)
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
