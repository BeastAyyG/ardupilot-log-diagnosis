from importlib import metadata

import src.cli.main as cli_main


def _version_action(monkeypatch):
    monkeypatch.setattr(cli_main, "_command_modules", lambda: ())
    parser = cli_main.build_parser()
    return next(action for action in parser._actions if action.dest == "version")


def test_source_checkout_uses_deterministic_version_fallback(monkeypatch):
    monkeypatch.setattr(
        metadata,
        "version",
        lambda _: (_ for _ in ()).throw(metadata.PackageNotFoundError()),
    )

    action = _version_action(monkeypatch)

    assert action.version == "ardupilot-log-diagnosis, version 0+source"


def test_installed_metadata_version_is_preserved(monkeypatch):
    monkeypatch.setattr(metadata, "version", lambda _: "9.8.7")

    action = _version_action(monkeypatch)

    assert action.version == "ardupilot-log-diagnosis, version 9.8.7"
