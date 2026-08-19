from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from src.integrations.read_only_tools import dispatch_tool
from src.parser.catalogue import get_catalogue_manifest
from src.parser.capabilities import get_capability_registry
from src.web.app import app, catalogue_coverage


def test_catalogue_manifest_covers_every_named_public_entry():
    manifest = get_catalogue_manifest()
    assert manifest["schema_version"] == "catalogue-coverage.v1"
    assert manifest["entry_count"] >= 12
    assert len(manifest["entries"]) == manifest["entry_count"]
    assert all(item["id"] and item["name"] and item["coverage"] for item in manifest["entries"])
    assert {"implemented_local", "implemented_subset", "review_only", "external_only"}.issubset(manifest["coverage_counts"])


def test_catalogue_manifest_is_read_only_and_has_callable_entry_points():
    manifest = get_catalogue_manifest()
    capability_ids = {item["id"] for item in get_capability_registry()}
    assert manifest["read_only"] is True
    assert any(item["entry_points"] for item in manifest["entries"] if item["coverage"] != "external_only")
    assert all(item.get("scope_note") for item in manifest["entries"])
    assert all(set(item["capability_ids"]).issubset(capability_ids) for item in manifest["entries"])


def test_catalogue_available_through_api_and_tool_facade():
    api_result = asyncio.run(catalogue_coverage())
    tool_result = dispatch_tool("catalogue_coverage")
    assert api_result["schema_version"] == "catalogue-coverage.v1"
    assert tool_result["entry_count"] == api_result["entry_count"]
    response = TestClient(app).get("/api/catalogue")
    assert response.status_code == 200
    assert response.json()["entry_count"] == api_result["entry_count"]


def test_every_read_only_tool_handles_an_empty_contract_without_crashing():
    from src.integrations.read_only_tools import TOOL_DEFINITIONS, dispatch_tool

    for definition in TOOL_DEFINITIONS:
        result = dispatch_tool(definition["name"], {"parsed": {}, "report": {}, "reports": [], "mission": [], "rules": []})
        assert isinstance(result, dict), definition["name"]
