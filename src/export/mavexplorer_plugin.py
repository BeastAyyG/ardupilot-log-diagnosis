from __future__ import annotations

import os
from typing import Any, Optional


class MAVExplorerDiagnosisPlugin:
    """
    Plugin for MAVExplorer (part of MAVProxy / ArduPilot command-line tools).
    Allows running BeastAyyG diagnostic engine directly on the currently loaded log file
    from within MAVExplorer interactive session (`beast_diagnose` / `diagnosis`).
    """

    def __init__(self, mavexplorer_instance: Any = None):
        self.me = mavexplorer_instance
        self.last_report: Optional[str] = None

    def init_plugin(self) -> None:
        if self.me and hasattr(self.me, "mpstate") and hasattr(self.me.mpstate, "command_map"):
            self.me.mpstate.command_map["beast_diagnose"] = (
                self.cmd_beast_diagnose,
                "Run BeastAyyG AI Log Diagnosis on current .BIN",
            )
            self.me.mpstate.command_map["amc_export"] = (
                self.cmd_amc_export,
                "Export diagnosed root causes to AMC configuration workflow JSON",
            )

    def cmd_beast_diagnose(self, args: list[str]) -> None:
        if not self.me or not hasattr(self.me, "filename") or not self.me.filename:
            print("[ERROR] No log file currently opened in MAVExplorer.")
            return

        logfile = self.me.filename
        if not os.path.exists(logfile):
            print(f"[ERROR] Log file path does not exist: {logfile}")
            return

        print(f"[BeastAyyG] Analyzing {logfile} with Hybrid Physics+ML Diagnostic Engine...")
        try:
            from src.cli.commands.common import load_parsed_and_features
            from src.diagnosis.hybrid_engine import HybridEngine
            from src.diagnosis.parameter_validation import validate_parameters
            from src.cli.formatter import DiagnosisFormatter

            parsed, features = load_parsed_and_features(logfile)
            engine = HybridEngine()
            diagnoses = engine.diagnose(features)
            parameter_warnings = validate_parameters(
                parsed.get("parameters", {}),
                features,
                features.get("_metadata", {}).get("vehicle_type", "Unknown"),
            )

            formatter = DiagnosisFormatter()
            metadata = features.get("_metadata", {})
            output = formatter.format_terminal(
                diagnoses,
                metadata,
                parameter_warnings=parameter_warnings,
                explain_data=getattr(engine, "last_explain_data", None),
            )
            self.last_report = output
            print("\n" + output)
        except Exception as exc:
            print(f"[ERROR] BeastAyyG Diagnostic Engine failed: {exc}")

    def cmd_amc_export(self, args: list[str]) -> None:
        if not self.me or not hasattr(self.me, "filename") or not self.me.filename:
            print("[ERROR] No log file currently opened in MAVExplorer.")
            return

        logfile = self.me.filename
        out_path = args[0] if args else logfile + ".amc_workflow.json"

        print(f"[BeastAyyG] Generating AMC Workflow recommendations for {logfile}...")
        try:
            from src.cli.commands.common import load_parsed_and_features
            from src.diagnosis.hybrid_engine import HybridEngine
            from src.diagnosis.parameter_validation import validate_parameters
            from src.export.amc_exporter import AMCExporter

            parsed, features = load_parsed_and_features(logfile)
            engine = HybridEngine()
            diagnoses = engine.diagnose(features)
            parameter_warnings = validate_parameters(
                parsed.get("parameters", {}),
                features,
                features.get("_metadata", {}).get("vehicle_type", "Unknown"),
            )

            exporter = AMCExporter()
            json_payload = exporter.export_json(
                diagnoses,
                features.get("_metadata", {}),
                parameter_warnings=parameter_warnings,
            )
            with open(out_path, "w") as f:
                f.write(json_payload)
            print(f"[BeastAyyG] Successfully exported AMC workflow to: {out_path}")
        except Exception as exc:
            print(f"[ERROR] AMC Workflow Export failed: {exc}")


def init(mavexplorer_instance: Any) -> MAVExplorerDiagnosisPlugin:
    """Entry point when dynamically loaded by MAVExplorer plugin manager."""
    plugin = MAVExplorerDiagnosisPlugin(mavexplorer_instance)
    plugin.init_plugin()
    return plugin
