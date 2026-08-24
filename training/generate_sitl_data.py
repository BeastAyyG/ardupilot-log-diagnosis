"""Inspect the authoritative scenario catalogue used by the SITL factory."""

from training.sitl_data_factory import FAILURE_CONFIGS

SITL_FAILURE_CONFIGS = FAILURE_CONFIGS


def print_sitl_commands(failure_type: str):
    config = SITL_FAILURE_CONFIGS.get(failure_type)
    if not config:
        print(f"Unknown failure type: {failure_type}")
        return

    print(f"--- Scenario family: {failure_type} ---")
    print(f"Label: {config['label']}")
    if config.get("startup"):
        print("Startup parameter choices:", config["startup"])
    if config.get("injection"):
        print("In-flight parameter choices:", config["injection"])
    else:
        print("No fault injection; this is a domain-randomized healthy flight.")
    print("Create reproducible runs with: python -m training.sitl_data_factory plan ...")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print_sitl_commands(sys.argv[1])
    else:
        print("Available failures:")
        for k in SITL_FAILURE_CONFIGS:
            print(f" - {k}")
