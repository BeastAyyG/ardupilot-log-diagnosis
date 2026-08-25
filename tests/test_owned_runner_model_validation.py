from pathlib import Path

import pytest

from synthetic_data.owned_runner import _pinned_vehicle_model


def _source(root: Path, body: str) -> None:
    path = root / "Tools" / "autotest" / "pysim"
    path.mkdir(parents=True)
    (path / "vehicleinfo.py").write_text(body, encoding="utf-8")


def test_model_mapping_is_read_from_pinned_vehicleinfo(tmp_path: Path) -> None:
    _source(
        tmp_path,
        """
class VehicleInfo:
    def __init__(self):
        self.options = {
            'ArduCopter': {'frames': {
                'quad': {'model': '+', 'waf_target': 'bin/arducopter'},
                'hexa': {'waf_target': 'bin/arducopter'},
            }}
        }
""",
    )

    model, digest = _pinned_vehicle_model(tmp_path, "quad")

    assert model == "+"
    assert len(digest) == 64


def test_model_mapping_defaults_to_frame_when_source_omits_model(tmp_path: Path) -> None:
    _source(
        tmp_path,
        "self.options = {'ArduCopter': {'frames': {'hexa': {'waf_target': 'bin/arducopter'}}}}",
    )

    assert _pinned_vehicle_model(tmp_path, "hexa")[0] == "hexa"


def test_model_mapping_rejects_wrong_vehicle_binary_target(tmp_path: Path) -> None:
    _source(
        tmp_path,
        "self.options = {'ArduCopter': {'frames': {'quad': {'model': '+', 'waf_target': 'bin/ardurover'}}}}",
    )

    with pytest.raises(RuntimeError, match="not bound to bin/arducopter"):
        _pinned_vehicle_model(tmp_path, "quad")

