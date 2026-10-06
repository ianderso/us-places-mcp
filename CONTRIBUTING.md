# Contributing

Issues and pull requests are welcome. This file says how the project is put
together and what a change is expected to carry.

## Setting up

```bash
git clone https://github.com/ianderso/us-places-mcp
cd us-places-mcp
uv sync --extra dev
```

Before sending a change, run what CI runs:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

The suite is mocked with [respx](https://lundberg.github.io/respx/) against
recorded answers. It must never touch the live services: OpenHistoricalMap runs
on donated capacity, and CI should not depend on any service being up. The
downloaded datasets are tested on small slices of the real files; never commit
a whole one.

## Where things live

| Path | What it holds |
| --- | --- |
| `src/us_places_mcp/server.py` | The tools. Their docstrings and `Field` descriptions *are* the published tool descriptions and schema. |
| `src/us_places_mcp/fetch.py` | The cached, paced HTTP client, its downloads, and the host allowlist. |
| `src/us_places_mcp/counties.py` | County-at-date logic over the Newberry atlas. |
| `src/us_places_mcp/legal.py` | The land-description parser. |
| `src/us_places_mcp/plss.py` | BLM PLSS queries and geometry. |
| `src/us_places_mcp/landfiles.py` | From a patent's authority to its case file. |
| `src/us_places_mcp/glo.py` | GLO Records link builders. |
| `src/us_places_mcp/gnis.py` | GNIS: the live `find` search and the August 2021 archive. |
| `src/us_places_mcp/topo.py` | Historical topographic maps from TNM Access. |
| `src/us_places_mcp/postoffices.py` | The post-office dataset: Dataverse's record, loading and queries. |
| `src/us_places_mcp/datasets.py` | Downloading, checking and keeping the two datasets. |
| `src/us_places_mcp/tables.py` | Meridians, states, and which land was federal. |
| `docs/API-NOTES.md` | What each service was observed to do, and when. |
| `docs/DESIGN.md` | Why the server is shaped the way it is. |
| `tests/fixtures/` | Recorded answers and the tool-schema snapshot. |
| `tests/test_tool_contract.py` | Tests over the tool surface as a client sees it. |
| `tests/live_check.py` | The one script that talks to the live services, run by hand. Not collected. |

## What a change carries

**A test that fails without it.** Bug fixes especially: reproduce the bug as a
test first. A land description the parser misreads belongs in
`tests/test_legal.py`'s golden cases.

**Descriptions written for the model.** A tool's docstring is what a model
reads when choosing and calling it. The combined descriptions have a ceiling
(`DESCRIPTION_BUDGET` in `tests/test_tool_contract.py`), because they are sent
on every session. Raise it deliberately, in a pull request of its own.

**The warnings, kept.** The county then is not the county now; a tract is not
a house; a patent's signature date is not the settlement date. A contract test
checks the descriptions still say so.

**A structured result, never an exception.** Every tool catches its failures
and returns an `error` envelope. A sweep test calls every tool with the API
failing and fails if one raises.

**Nothing that writes, and nothing that scrapes GLO Records.** See
[docs/DESIGN.md](docs/DESIGN.md#out-of-scope-by-decision).

**A new fixture recorded, not invented,** when a change depends on how a
service answers, with what was observed and when added to `docs/API-NOTES.md`.

**The snapshot, when the surface changes.** Renaming or adding a tool or a
parameter fails the snapshot test on purpose. Regenerate it with
`uv run python -m tests.regen_tool_snapshot`, update the README tables, and add
a `CHANGELOG.md` entry.

## Releasing

A maintainer bumps `__version__` in `src/us_places_mcp/__init__.py` and
both versions in `server.json`, moves the changelog's Unreleased entries under
the new version, and publishes a GitHub release tagged `v<version>`. The
release workflow builds the tag, publishes to PyPI by Trusted Publishing, and
lists the version in the MCP Registry.
