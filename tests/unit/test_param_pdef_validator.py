from src.core.remediation.param_pdef_validator import load_pdef, validate_against_pdef


def test_pdef_validator_reads_ranges_and_unknowns(tmp_path):
    path = tmp_path / "apm.pdef.xml"
    path.write_text(
        '<params><param name="TEST_GAIN" type="float" min="0" max="1" />'
        '<param name="MODE" type="enum" values="0|1" /></params>',
        encoding="utf-8",
    )

    definitions = load_pdef(path)
    issues = validate_against_pdef({"TEST_GAIN": 2.0, "MODE": 3, "UNKNOWN": 1}, definitions)

    assert definitions["TEST_GAIN"].maximum == 1.0
    assert [(issue.name, issue.kind) for issue in issues] == [
        ("MODE", "enum"),
        ("TEST_GAIN", "range"),
        ("UNKNOWN", "unknown"),
    ]
