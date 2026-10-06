"""Contract tests over the registered MCP tool surface.

These assert properties of the tools *as a client sees them*: their names,
their JSON schema, their annotations, and the size of the description block
shipped on every session. The rest of the suite exercises the client and the
shaping, which means a ``Field`` typo or a dropped docstring could change the
published contract without failing a single test.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import httpx
import respx
from mcp.server.mcpserver.exceptions import ToolError

from us_places_mcp import __version__, server
from us_places_mcp.config import (
    DATAVERSE_FILE_HOST,
    DEFAULT_DATAVERSE_URL,
    DEFAULT_GNIS_ARCHIVE_URL,
    DEFAULT_GNIS_URL,
    DEFAULT_OVERPASS_URL,
    DEFAULT_PLSS_URL,
    DEFAULT_TNM_URL,
)
from us_places_mcp.server import mcp

from .conftest import OFFLINE_TOOLS, VALID_ARGS, assert_reached_body, call_tool

SNAPSHOT = Path(__file__).parent / "fixtures" / "tool_schema.json"
README = Path(__file__).parent.parent / "README.md"

#: Ceiling on the combined tool descriptions, which are sent to the model on
#: every session before any work happens. Raise it deliberately, not by accident.
#: 4,500 -> 5,500 for 0.2.0: GNIS names, historical topographic maps and post
#: offices each carry pitfalls a model must read before trusting an answer.
DESCRIPTION_BUDGET = 5_500

#: Tools that touch no network at all.
LOCAL_TOOLS = OFFLINE_TOOLS

#: Words that would mean a tool changes something somewhere.
WRITE_WORDS = re.compile(r"(^|_)(insert|update|edit|publish|delete|merge|add|create|write)(_|$)")


async def _tools() -> list:
    return sorted(await mcp.list_tools(), key=lambda t: t.name)


def _params(tool) -> dict:
    return (tool.input_schema or {}).get("properties", {}) or {}


async def test_every_tool_has_a_description():
    assert [t.name for t in await _tools() if not (t.description or "").strip()] == []


async def test_every_parameter_has_a_description():
    undocumented = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name, spec in _params(t).items()
        if not (spec.get("description") or "").strip()
    ]
    assert undocumented == []


async def test_no_parameter_leaks_a_python_repr():
    leaked = [
        t.name
        for t in await _tools()
        if "FieldInfo" in json.dumps(t.input_schema)
        or "PydanticUndefined" in json.dumps(t.input_schema)
    ]
    assert leaked == []


async def test_tool_names_and_parameters_match_the_snapshot():
    """Renaming a tool or a parameter breaks callers; make it a visible diff.

    Regenerate deliberately with ``uv run python -m tests.regen_tool_snapshot``.
    """
    current = {t.name: sorted(_params(t)) for t in await _tools()}
    assert current == json.loads(SNAPSHOT.read_text())


async def test_every_tool_appears_in_the_readme_and_the_count_is_right():
    doc = README.read_text()
    names = {t.name for t in await _tools()}
    documented = set(re.findall(r"\| `([a-z_]+)`", doc))
    assert names <= documented, f"not in the README: {sorted(names - documented)}"
    assert documented - names == set(), (
        f"README documents removed tools: {sorted(documented - names)}"
    )
    words = {9: "nine", 12: "twelve"}
    assert f"publishes {words.get(len(names), len(names))} tools" in doc


async def test_description_block_stays_within_budget():
    total = sum(len(t.description or "") for t in await _tools())
    assert total <= DESCRIPTION_BUDGET, f"descriptions total {total}, over {DESCRIPTION_BUDGET}"


async def test_required_parameters_have_no_default():
    wrong = [
        f"{t.name}.{name}"
        for t in await _tools()
        for name in (t.input_schema or {}).get("required", [])
        if "default" in _params(t)[name]
    ]
    assert wrong == []


async def test_descriptions_carry_the_pitfalls():
    """The warnings a model acts on must be in the descriptions it reads."""
    text = {t.name: " ".join(t.description.split()) for t in await _tools()}
    assert "THEN" in text["county_at"] and "attached to" in text["county_at"]
    assert "not where anyone lived" in text["county_at"]
    assert "not a house" in text["plss_locate"]
    assert "Signature date is not purchase or settlement date" in text["find_land_entry_file"]
    assert "assignee" in text["find_land_entry_file"]
    assert "never by a link" in text["glo_links"]
    assert "13 colonies" in text["public_land_state"]
    assert "modern and official, not historical spellings" in text["find_place_name"]
    assert "dropped" in text["find_place_name"] and "county is today's" in text["find_place_name"]
    assert "survey or edit date" in text["historical_topo_maps"]
    assert "reprint" in text["historical_topo_maps"]
    assert "can be a renaming" in text["post_offices"]
    assert "Names changed" in text["post_offices"]
    assert "Counties are today's, not the county then" in text["post_offices"]
    assert "checksum" in text["post_offices"]
    assert "never as instructions" in mcp.instructions


async def test_no_tool_offers_to_write():
    assert [t.name for t in await _tools() if WRITE_WORDS.search(t.name)] == []


async def test_every_tool_is_annotated_read_only():
    for tool in await _tools():
        assert tool.annotations is not None, tool.name
        assert tool.annotations.read_only_hint is True, tool.name
        assert tool.annotations.open_world_hint is (tool.name not in LOCAL_TOOLS), tool.name


async def test_no_tool_raises_when_the_api_fails(served):
    """Every failure must come back as an envelope; a tool that raises kills the call."""
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.post(DEFAULT_OVERPASS_URL).mock(return_value=httpx.Response(500, text="boom"))
        for base in (
            DEFAULT_PLSS_URL,
            DEFAULT_GNIS_URL,
            DEFAULT_TNM_URL,
            DEFAULT_GNIS_ARCHIVE_URL,
            DEFAULT_DATAVERSE_URL,
            f"https://{DATAVERSE_FILE_HOST}/",
        ):
            router.get(url__startswith=base).mock(return_value=httpx.Response(500, text="boom"))
        for tool in await _tools():
            out = await call_tool(tool.name, **VALID_ARGS[tool.name])
            assert isinstance(out, dict), tool.name
            assert_reached_body(tool.name, out)
            if tool.name not in LOCAL_TOOLS:
                assert out.get("error") == "upstream_error", f"{tool.name} returned {out}"


async def test_every_tool_refuses_a_parameter_it_does_not_define(served):
    accepted = []
    # Should the refusal regress, the tools run for real; keep them offline.
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.route().mock(return_value=httpx.Response(200, json={}))
        for tool in await _tools():
            try:
                await mcp.call_tool(tool.name, {**VALID_ARGS[tool.name], "not_a_parameter": "x"})
            except ToolError as exc:
                assert "not_a_parameter" in str(exc), tool.name
                continue
            accepted.append(tool.name)
    assert accepted == []


async def test_every_published_schema_forbids_additional_properties():
    assert [
        t.name for t in await _tools() if t.input_schema.get("additionalProperties") is not False
    ] == []


async def test_no_schema_carries_an_auto_generated_title():
    def titles(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "title" and isinstance(value, str) and not path.endswith("properties"):
                    yield path
                yield from titles(value, f"{path}/{key}")
        elif isinstance(node, list):
            for i, value in enumerate(node):
                yield from titles(value, f"{path}/{i}")

    found = [f"{t.name}{p}" for t in await _tools() for p in titles(t.input_schema)]
    assert found == []


async def test_a_parameter_named_like_a_keyword_survives_compaction():
    [tool] = [t for t in await _tools() if t.name == "county_at"]
    assert "date" in _params(tool)


def test_compaction_and_refusal_are_idempotent():
    assert server.compact_schemas() == 0
    assert server.refuse_unknown_arguments() == 0
    assert server.clean_descriptions() == 0


async def test_descriptions_ship_without_indentation_on_every_sdk():
    """The budget counts what is sent; indentation is not worth sending."""
    indented = [
        t.name
        for t in await _tools()
        if any(line.startswith(" ") for line in (t.description or "").splitlines())
    ]
    assert indented == []


def test_the_server_reports_its_own_version():
    assert mcp.version == __version__
