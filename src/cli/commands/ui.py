import argparse


def register(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("ui", help="Launch the interactive Web Dashboard")
    parser.add_argument("--port", type=int, default=8000, help="Port to run the web server on")
    parser.add_argument("--mavlink", type=str, help="Optional MAVLink connection string for real-time live streaming")
    parser.add_argument("--stream-auth-token", type=str, default="ardupilot", help="Auth token for the WebSocket live stream")
    parser.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    import sys
    import os

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
    if args.mavlink:
        print(f"Live Stream MAVLink Source: {args.mavlink}")
        os.environ["MAVLINK_CONNECTION"] = args.mavlink
    os.environ["MAVLINK_AUTH_TOKEN"] = args.stream_auth_token

    print(f"Open your browser at: http://localhost:{args.port}\n")
    uvicorn.run("src.web.app:app", host="127.0.0.1", port=args.port, reload=False)
