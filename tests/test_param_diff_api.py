import asyncio
import io

from starlette.datastructures import UploadFile

from src.web.app import parameter_diff, parameter_validate


def test_api_parameter_diff(tmp_path):
    before = UploadFile(file=io.BytesIO(b"ATC_RAT_RLL_P,0.1\n"), filename="before.param")
    after = UploadFile(file=io.BytesIO(b"ATC_RAT_RLL_P,0.2\n"), filename="after.param")
    report = asyncio.run(parameter_diff(before, after))
    assert report["changed_count"] == 1


def test_api_parameter_validation_is_read_only():
    upload = UploadFile(file=io.BytesIO(b"BATT_LOW_VOLT,-1\n"), filename="aircraft.param")
    report = asyncio.run(parameter_validate(upload))
    assert report["status"] == "invalid"
    assert report["write_parameters"] is False
