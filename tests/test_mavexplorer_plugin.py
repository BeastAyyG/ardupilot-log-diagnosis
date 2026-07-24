from src.export.mavexplorer_plugin import init, MAVExplorerDiagnosisPlugin


class MockMPState:
    def __init__(self):
        self.command_map = {}


class MockMAVExplorer:
    def __init__(self, filename=None):
        self.mpstate = MockMPState()
        self.filename = filename


def test_mavexplorer_plugin_init():
    me = MockMAVExplorer("test.BIN")
    init(me)
    assert "beast_diagnose" in me.mpstate.command_map
    assert "amc_export" in me.mpstate.command_map


def test_mavexplorer_plugin_missing_file(capsys):
    me = MockMAVExplorer("nonexistent.BIN")
    plugin = MAVExplorerDiagnosisPlugin(me)
    plugin.cmd_beast_diagnose([])
    captured = capsys.readouterr()
    assert "[ERROR] Log file path does not exist" in captured.out
