import argparse


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ui", help="Launch the interactive Web Dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the web server on")
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

    try:
        import uvicorn
    except ImportError:
        print("\n[ERROR] Optional web UI dependencies are not installed.")
        print("Install them with: pip install -e .[web]")
        raise SystemExit(1)

    print("\nLaunching ArduPilot Log Diagnosis Dashboard...")
    print(f"Open your browser at: http://localhost:{args.port}\n")
    uvicorn.run("src.web.app:app", host="127.0.0.1", port=args.port, reload=False)
