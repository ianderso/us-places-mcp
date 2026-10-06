"""Configuration from environment variables.

==============================  ==============================================
``US_PLACES_OVERPASS_URL``       OpenHistoricalMap's Overpass endpoint.
``US_PLACES_PLSS_URL``           BLM's national PLSS (CadNSDI) map service.
``US_PLACES_GNIS_URL``           USGS's GNIS map service (The National Map).
``US_PLACES_GNIS_ARCHIVE_URL``   Where USGS keeps the August 2021 GNIS state
                                 files.
``US_PLACES_TNM_URL``            The National Map's TNM Access products API.
``US_PLACES_DATAVERSE_URL``      Harvard Dataverse, which holds the US post
                                 offices dataset.
``US_PLACES_CACHE_DIR``          Directory for the on-disk response cache and
                                 the downloaded datasets.
``US_PLACES_TIMEOUT``            HTTP timeout in seconds.
``US_PLACES_CONTACT``            An email address or URL appended to the
                                 User-Agent, so the services can reach whoever
                                 runs this server.
==============================  ==============================================

None is required: every service is public and needs no key. A ``.env`` file
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

#: USGS's Geographic Names Information System, as The National Map serves it.
DEFAULT_GNIS_URL = "https://carto.nationalmap.gov/arcgis/rest/services/geonames/MapServer"

#: The folder of GNIS state files frozen on 25 August 2021, before GNIS dropped
#: cemeteries, churches, schools, post offices and other built features.
DEFAULT_GNIS_ARCHIVE_URL = (
    "https://prd-tnm.s3.amazonaws.com/StagedProducts/GeographicNames/Archive/MainDomestic"
)

#: The National Map's product search, which lists the historical topographic maps.
DEFAULT_TNM_URL = "https://tnmaccess.nationalmap.gov/api/v1/products"

#: Harvard Dataverse, home of the Blevins/Helbock US post offices dataset.
DEFAULT_DATAVERSE_URL = "https://dataverse.harvard.edu"

#: Where Harvard Dataverse redirects a file download. Not a setting: the
#: redirect is Dataverse's choice, and this is the one host it may send us to.
DATAVERSE_FILE_HOST = "dvn-cloud-iqss.s3.amazonaws.com"


class ConfigError(RuntimeError):
    """Raised when a setting is present but unusable."""


@dataclass
class Config:
    """Resolved server configuration.

    The hosts of the URLs, and Dataverse's file store, are the only hosts the
    server will contact.
    """

    overpass_url: str = DEFAULT_OVERPASS_URL
    plss_url: str = DEFAULT_PLSS_URL
    gnis_url: str = DEFAULT_GNIS_URL
    gnis_archive_url: str = DEFAULT_GNIS_ARCHIVE_URL
    tnm_url: str = DEFAULT_TNM_URL
    dataverse_url: str = DEFAULT_DATAVERSE_URL
    cache_dir: Path = field(default_factory=lambda: Path.home() / ".cache" / "us-places-mcp")
    timeout: float = 60.0
    contact: str = ""
    #: Where downloaded datasets live; None means ``<cache_dir>/data``.
    datasets_dir: Path | None = None

    @property
    def data_dir(self) -> Path:
        """The directory for downloaded datasets: never the repository."""
        return self.datasets_dir or self.cache_dir / "data"


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
    if raw := (os.environ.get("US_PLACES_GNIS_URL") or "").strip():
        cfg.gnis_url = _https_url("US_PLACES_GNIS_URL", raw).rstrip("/")
    if raw := (os.environ.get("US_PLACES_GNIS_ARCHIVE_URL") or "").strip():
        cfg.gnis_archive_url = _https_url("US_PLACES_GNIS_ARCHIVE_URL", raw).rstrip("/")
    if raw := (os.environ.get("US_PLACES_TNM_URL") or "").strip():
        cfg.tnm_url = _https_url("US_PLACES_TNM_URL", raw)
    if raw := (os.environ.get("US_PLACES_DATAVERSE_URL") or "").strip():
        cfg.dataverse_url = _https_url("US_PLACES_DATAVERSE_URL", raw).rstrip("/")
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
