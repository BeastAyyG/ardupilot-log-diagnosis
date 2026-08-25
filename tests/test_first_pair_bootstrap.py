import pytest

from synthetic_data.first_pair import _bootstrap_plan


@pytest.mark.parametrize("frame,expected", [("quad", 1.0), ("hexa", 2.0), ("octa", 3.0)])
def test_inventory_bootstrap_seeds_requested_frame_class(frame, expected) -> None:
    plan = _bootstrap_plan("a" * 40, "b" * 64, frame)

    assert plan["startup_parameters"] == {"FRAME_CLASS": expected}


def test_inventory_bootstrap_rejects_unverified_frame() -> None:
    with pytest.raises(ValueError, match="unsupported first-pair frame"):
        _bootstrap_plan("a" * 40, "b" * 64, "plane")

