"""Configuration from environment variables.

=========================  ===================================================
``US_PLACES_OVERPASS_URL``  OpenHistoricalMap's Overpass endpoint.
``US_PLACES_PLSS_URL``      BLM's national PLSS (CadNSDI) map service.
``US_PLACES_CACHE_DIR``     Directory for the on-disk response cache.
``US_PLACES_TIMEOUT``       HTTP timeout in seconds.
``US_PLACES_CONTACT``       An email address or URL appended to the
                            User-Agent, so either service can reach whoever
                            runs this server.
=========================  ===================================================

None is required: both services are public and need no key. A ``.env`` file
in the working directory supplies any of these that the environment does not.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

#: OpenHistoricalMap's public Overpass API.
DEFAULT_OVERPASS_URL = "https://overpass-api.openhistoricalmap.org/api/interpreter"

#: BLM's national Public Land Survey System map service (CadNSDI).
DEFAULT_PLSS_URL = (
    "https://gis.blm.gov/arcgis/rest/services/Cadastral/BLM_Natl_PLSS_CadNSDI/MapServer"
)


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    The hosts of the two URLs are the only hosts the server will contact.
    """

    overpass_url: str = DEFAULT_OVERPASS_URL
    plss_url: str = DEFAULT_PLSS_URL
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "us-places-mcp")
    timeout: float = 60.0
    contact: str = ""


def load_config() -> Config:
    """Load configuration from the environment.

    A ``.env`` file in the working directory is read if present; real
    environment variables win. Only the working directory is consulted, not
    its parents and not the directory the package is installed in.

    Raises
    ------
    ConfigError
        If a URL is not https with a host, the timeout is not a positive
        number, or the contact could break the User-Agent header. Surfaces on
        the first tool call as a ``not_configured`` result.
    """
    load_dotenv(Path.cwd() / ".env")

    cfg = Config()
    if raw := (os.environ.get("US_PLACES_OVERPASS_URL") or "").strip():
        cfg.overpass_url = _https_url("US_PLACES_OVERPASS_URL", raw)
    if raw := (os.environ.get("US_PLACES_PLSS_URL") or "").strip():
        cfg.plss_url = _https_url("US_PLACES_PLSS_URL", raw).rstrip("/")
    if raw := os.environ.get("US_PLACES_CACHE_DIR"):
        cfg.cache_dir = Path(raw).expanduser()
    if raw := os.environ.get("US_PLACES_TIMEOUT"):
        cfg.timeout = _positive("US_PLACES_TIMEOUT", raw)
    if raw := os.environ.get("US_PLACES_CONTACT"):
        cfg.contact = _contact(raw)
    return cfg


def _https_url(name: str, raw: str) -> str:
    parts = urlsplit(raw)
    if parts.scheme != "https" or not parts.hostname:
        raise ConfigError(f"{name} must be an https URL with a host; got {raw!r}.")
    return raw


def _positive(name: str, raw: str) -> float:
    try:
        value = float(raw.strip())
    except ValueError:
        raise ConfigError(f"{name} must be a number; got {raw!r}.") from None
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{name} must be greater than zero; got {raw!r}.")
    return value


def _contact(raw: str) -> str:
    """Keep a contact string safe to place inside a User-Agent comment."""
    text = raw.strip()
    if any(ch in text for ch in "\r\n()") or not text.isprintable():
        raise ConfigError(
            "US_PLACES_CONTACT must be one line with no parentheses, such as an "
            f"email address or a URL; got {raw!r}."
        )
    return text
