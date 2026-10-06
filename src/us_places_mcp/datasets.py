"""Datasets fetched once into the cache directory, checked, and then read locally.

Two are used:

* **US post offices** (Blevins and Helbock, Harvard Dataverse, 31 MB), loaded
  whole the first time ``post_offices`` runs.
* **The GNIS archive of 25 August 2021,** one state file (up to 17 MB) the first
  time a search reaches that state.

Every download is checked before anything is kept: the post-office file
against the checksum Dataverse publishes for it, a GNIS file against the
ETag USGS's bucket reports (an MD5, or for a file uploaded in parts an MD5
of the parts' MD5s). A file that fails is deleted and the tool says so; a
partial load is never left behind. They live under ``<cache dir>/data``,
never in the repository, and each tool's result announces a download when it
happens.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import re
import time
import uuid
from pathlib import Path

from . import gnis, postoffices
from .config import Config
from .fetch import DAY, Fetcher

#: No file this server downloads is larger than this.
MAX_DOWNLOAD = 64 * 1024 * 1024

#: Part sizes an S3 multipart upload is likely to have used, most likely first.
_MIB = 1024 * 1024
PART_SIZES = (8 * _MIB, 16 * _MIB, 5 * _MIB, 15 * _MIB, 32 * _MIB, 64 * _MIB)

_ETAG = re.compile(r"([0-9a-f]{32})(?:-(\d+))?")


class DataError(RuntimeError):
    """A download that failed its check, or a file not in the expected shape."""


_locks: dict[str, asyncio.Lock] = {}


def _lock(name: str) -> asyncio.Lock:
    return _locks.setdefault(name, asyncio.Lock())


def _digest(path: Path, algorithm: str) -> str:
    try:
        h = hashlib.new(algorithm, usedforsecurity=False)
    except ValueError:
        raise DataError(f"cannot check a {algorithm!r} checksum") from None
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _multipart_etag(path: Path, part_size: int) -> str:
    parts = []
    with path.open("rb") as fh:
        while chunk := fh.read(part_size):
            parts.append(hashlib.md5(chunk, usedforsecurity=False).digest())
    return f"{hashlib.md5(b''.join(parts), usedforsecurity=False).hexdigest()}-{len(parts)}"


def check_s3_etag(path: Path, size: int, etag: str) -> str:
    """Check a file against an S3 ETag; say how. Raises DataError on a mismatch."""
    m = _ETAG.fullmatch(etag.lower())
    if not m:
        raise DataError(f"the server gave no checksum to verify the file against ({etag!r})")
    if m.group(2) is None:
        if _digest(path, "md5") == m.group(1):
            return "MD5 matches the bucket's ETag"
    else:
        parts = int(m.group(2))
        for part_size in PART_SIZES:
            if math.ceil(size / part_size) == parts and _multipart_etag(path, part_size) == etag:
                return f"MD5 of its {parts} upload parts matches the bucket's ETag"
    raise DataError("the file does not match the checksum the server published for it")


def _mb(size: int) -> str:
    return f"{size / 1_000_000:.1f} MB"


# --------------------------------------------------------------------------- #
# US post offices
# --------------------------------------------------------------------------- #
async def post_offices_db(cfg: Config, fetcher: Fetcher) -> tuple[Path, dict | None]:
    """The local post-office database, and an announcement if it was downloaded now."""
    db = cfg.data_dir / postoffices.DB_NAME
    if db.exists():
        return db, None
    async with _lock(str(db)):
        if db.exists():
            return db, None
        try:
            entry = postoffices.dataset_file(
                await fetcher.get_json(
                    f"{cfg.dataverse_url}/api/datasets/:persistentId/",
                    {"persistentId": postoffices.DOI},
                    ttl=DAY,
                )
            )
        except postoffices.DatasetChanged as exc:
            raise DataError(str(exc)) from None
        got = await fetcher.download(
            f"{cfg.dataverse_url}/api/access/datafile/{entry['id']}?format=original",
            cfg.data_dir,
            max_bytes=MAX_DOWNLOAD,
        )
        building = db.with_name(f".{db.name}.{uuid.uuid4().hex}.tmp")
        try:
            if entry["size"] is not None and got.size != entry["size"]:
                raise DataError(
                    f"Dataverse lists {entry['size']:,} bytes; {got.size:,} arrived. "
                    "Nothing was kept."
                )
            if await asyncio.to_thread(_digest, got.path, entry["algorithm"]) != entry["checksum"]:
                raise DataError(
                    f"the download does not match Dataverse's {entry['algorithm'].upper()} "
                    "checksum. Nothing was kept; retry later."
                )
            meta = {
                "source": postoffices.DOI,
                "version": entry["version"],
                "file_id": str(entry["id"]),
                entry["algorithm"]: entry["checksum"],
                "bytes": str(got.size),
                "downloaded": time.strftime("%Y-%m-%d"),
            }
            try:
                count = await asyncio.to_thread(postoffices.build, got.path, building, meta)
            except postoffices.DatasetChanged as exc:
                raise DataError(str(exc)) from None
            os.replace(building, db)
        finally:
            got.path.unlink(missing_ok=True)
            building.unlink(missing_ok=True)
    return db, {
        "what": f"US Post Offices v{entry['version']} ({postoffices.DOI})",
        "file": postoffices.ORIGINAL_NAME,
        "bytes": got.size,
        "verified": f"{entry['algorithm'].upper()} matches Dataverse's ({entry['checksum']})",
        "offices": count,
        "saved_to": str(db),
        "note": f"Downloaded {_mb(got.size)} once; later calls read the local copy.",
    }


# --------------------------------------------------------------------------- #
# The GNIS archive of August 2021
# --------------------------------------------------------------------------- #
async def gnis_archive_db(cfg: Config, fetcher: Fetcher, state: str) -> tuple[Path, dict | None]:
    """The archive database with ``state`` loaded, and an announcement if loaded now."""
    db = cfg.data_dir / gnis.ARCHIVE_DB
    if state in gnis.archive_states(db):
        return db, None
    async with _lock(str(db)):
        if state in gnis.archive_states(db):
            return db, None
        url = gnis.archive_url(cfg.gnis_archive_url, state)
        got = await fetcher.download(url, cfg.data_dir, max_bytes=MAX_DOWNLOAD)
        try:
            how = await asyncio.to_thread(check_s3_etag, got.path, got.size, got.etag)
            try:
                count = await asyncio.to_thread(
                    gnis.load_archive, got.path, state, db, size=got.size, etag=got.etag
                )
            except ValueError as exc:
                raise DataError(str(exc)) from None
        finally:
            got.path.unlink(missing_ok=True)
    return db, {
        "what": f"GNIS archive of 25 August 2021, {state}",
        "file": gnis.archive_file(state),
        "bytes": got.size,
        "verified": how,
        "features_loaded": count,
        "saved_to": str(db),
        "note": f"Downloaded {_mb(got.size)} once; later searches in {state} read the local copy.",
    }


def status(cfg: Config) -> dict:
    """What has been downloaded, for cache_status. Reads only the local files."""
    out: dict = {"directory": str(cfg.data_dir)}
    offices = cfg.data_dir / postoffices.DB_NAME
    if offices.exists():
        try:
            meta = postoffices.read_meta(offices)
        except Exception:  # noqa: BLE001 - a damaged file is reported, not raised
            meta = {}
        out["us_post_offices"] = {
            "version": meta.get("version"),
            "offices": int(meta["offices"]) if meta.get("offices", "").isdigit() else None,
            "downloaded": meta.get("downloaded"),
            "bytes_on_disk": offices.stat().st_size,
        }
    else:
        out["us_post_offices"] = None
    archive = cfg.data_dir / gnis.ARCHIVE_DB
    states = gnis.archive_states(archive)
    out["gnis_2021_archive"] = (
        {"states": states, "bytes_on_disk": archive.stat().st_size} if states else None
    )
    return out
