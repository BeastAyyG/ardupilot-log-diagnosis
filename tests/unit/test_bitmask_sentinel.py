from src.core.ingestion.bitmask_sentinel import audit_logging


def test_audits_disabled_and_dropout_streams():
    audit = audit_logging(
        {
            "VIBE": [],
            "GPS": [{"TimeUS": 0}, {"TimeUS": 1_000_000}, {"TimeUS": 10_000_000}],
        },
        {"LOG_BITMASK": 0, "FRAME_CLASS": 1},
        expected_rates_hz={"GPS": 1.0},
        log_bit_mapping={"VIBE": 18},
        wired_sensors={"VIBE": True},
    )

    statuses = {finding.message: finding.status for finding in audit.findings}
    assert statuses == {"VIBE": "disabled", "GPS": "dropout"}
    assert not audit.preflight_ok
