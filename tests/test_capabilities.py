import asyncio

from src.parser.capabilities import get_capability_registry
from src.web.app import capabilities


def test_capability_registry_is_explicit():
    registry = get_capability_registry()
    by_id = {item["id"]: item for item in registry}
    assert by_id["hardware_report"]["status"] == "available"
    assert by_id["px4_ulog"]["status"] == "available_generic"
    assert by_id["px4_ulog"]["adapter_dependency"] == "pyulog"
    assert isinstance(by_id["px4_ulog"]["adapter_available"], bool)
    assert by_id["betaflight_blackbox"]["adapter_dependency"] == "orangebox"
    assert "required_messages" in by_id["fft_vibration"]


def test_capability_endpoint():
    result = asyncio.run(capabilities())
    assert result["schema_version"] == "capabilities.v1"
    assert any(item["id"] == "pdf_report" for item in result["capabilities"])
