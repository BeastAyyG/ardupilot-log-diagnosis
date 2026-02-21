import sys
from typing import Optional

from src.integration.cli import print_terminal_report, run_cli, run_diagnosis


class ArduPilotDiagnose:
    """
    Backward-compatible wrapper around the new integration CLI/runtime.
    """

    def __init__(self, model_path: Optional[str] = None, thresholds_path: Optional[str] = None):
        self.model_path = model_path
        self.thresholds_path = thresholds_path

    def analyze(self, bin_file: str):
        report = run_diagnosis(
            bin_file=bin_file,
            model_path=self.model_path,
            thresholds_path=self.thresholds_path,
        )
        print_terminal_report(report)
        return report


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    sys.exit(main())
