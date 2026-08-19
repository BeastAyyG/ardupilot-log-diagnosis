from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib.metadata
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect, Query
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, ValidationError

from src.web.schemas import AnalysisResponse, ChatRequest, ChatResponse

from src.diagnosis.decision_policy import evaluate_decision
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.parameter_validation import validate_parameters
from src.diagnosis.rule_engine import RuleEngine
from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser
from src.chat.assistant import ChatAssistant
from src.comparison.trend_analyzer import TrendAnalyzer
from src.reporting.hardware import HardwareReportBuilder
from src.parser.capabilities import capability_supports_format, get_capability_registry
from src.parser.catalogue import get_catalogue_manifest
from src.parser.file_format import detect_file_format, supported_format_kinds
from src.reporting.parameter_diff import diff_parameters, load_parameter_file
from src.reporting.parameter_validation import validate_parameters as validate_parameter_values
from src.reporting.parameter_catalog import list_parameters, load_catalog, search_parameters, validate_parameter
from src.web.live_stream import WebSocketManager, MAVLinkStreamer
from src.analysis.operations_metrics import acceptance_report, maintenance_comparison, build_baseline, compare_firmware_cohorts, location_recurrence
from src.analysis.weather_video import build_video_overlay, synchronize_video, video_overlay_text, weather_context
from src.analysis.temporal import temporal_evidence
from src.analysis.aynalike import run_aynalike_checks
from src.analysis.health_score import calculate_health_score
from src.analysis.windowing import extract_ml_feature_candidates
from src.analysis.methodic_review import review_methodic_step
from src.analysis.mission_plan import mission_compliance_report, validate_mission
from src.reporting.geo_export import to_gpx, to_kml, track_points
from src.reporting.plot_export import generate_plot
from src.reporting.graph_pack import generate_graph_pack
from src.reporting.raw_export import derived_series
from src.reporting.artifacts import artifact_manifest
from src.integrations.read_only_tools import TOOL_DEFINITIONS, dispatch_tool
from src.error_codes import ErrorCode, error_payload
from src.fleet.store import FleetStore
from src.fleet.alerts import evaluate_alerts, validate_webhook_url
from src.runtime_paths import default_models_dir


LOGGER = logging.getLogger(__name__)

try:
    APP_VERSION = importlib.metadata.version("ardupilot-log-diagnosis")
except importlib.metadata.PackageNotFoundError:
    APP_VERSION = "unknown"

# The API is intentionally self-observable without requiring an external
# metrics dependency.  These counters are process-local (each worker exposes
# its own values), which is the same model used by most scrape-based adapters.
_METRICS_LOCK = threading.Lock()
_REQUEST_COUNTS: dict[tuple[str, str, int], int] = {}
_REQUEST_DURATION_SUM: dict[tuple[str, str], float] = {}
_REQUEST_IN_FLIGHT = 0
_STARTED_AT = time.time()
_startup_runtime_state: dict[str, Any] = {}


def _request_id(value: str | None) -> str:
    """Return a bounded, log-safe request ID.

    Accepting a caller-supplied ID preserves trace correlation, but only for a
    conservative ASCII subset so logs and response headers cannot be used for
    header injection.  Invalid or oversized IDs are replaced with a UUID.
    """
    candidate = (value or "").strip()
    if candidate.isascii() and 1 <= len(candidate) <= 128 and all(
        char.isalnum() or char in {"-", "_", ".", ":"} for char in candidate
    ):
        return candidate
    return uuid.uuid4().hex


def _metric_path(request: Request) -> str:
    """Prefer the Starlette route template to avoid high-cardinality labels."""
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        return route_path
    return request.url.path or "/"


def _record_request(method: str, path: str, status_code: int, duration: float) -> None:
    global _REQUEST_IN_FLIGHT
    key = (method.upper(), path, int(status_code))
    duration_key = (method.upper(), path)
    with _METRICS_LOCK:
        _REQUEST_COUNTS[key] = _REQUEST_COUNTS.get(key, 0) + 1
        _REQUEST_DURATION_SUM[duration_key] = _REQUEST_DURATION_SUM.get(duration_key, 0.0) + duration
        _REQUEST_IN_FLIGHT = max(0, _REQUEST_IN_FLIGHT - 1)


def _metrics_payload() -> str:
    """Render a small Prometheus-compatible metrics snapshot."""
    with _METRICS_LOCK:
        counts = dict(_REQUEST_COUNTS)
        duration_sum = dict(_REQUEST_DURATION_SUM)
        in_flight = _REQUEST_IN_FLIGHT
    def escape_label(value: Any) -> str:
        return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    lines = [
        "# HELP ardupilot_info Build and runtime information.",
        "# TYPE ardupilot_info gauge",
        f'ardupilot_info{{version="{escape_label(APP_VERSION)}"}} 1',
        "# HELP ardupilot_uptime_seconds Process uptime in seconds.",
        "# TYPE ardupilot_uptime_seconds gauge",
        f"ardupilot_uptime_seconds {max(0.0, time.time() - _STARTED_AT):.6f}",
        "# HELP ardupilot_http_requests_in_flight Current requests being handled.",
        "# TYPE ardupilot_http_requests_in_flight gauge",
        f"ardupilot_http_requests_in_flight {in_flight}",
        "# HELP ardupilot_http_requests_total Total HTTP responses by route and status.",
        "# TYPE ardupilot_http_requests_total counter",
    ]
    for (method, path, status), count in sorted(counts.items()):
        lines.append(
            f'ardupilot_http_requests_total{{method="{escape_label(method)}",path="{escape_label(path)}",status="{status}"}} {count}'
        )
    lines.extend(
        [
            "# HELP ardupilot_http_request_duration_seconds_sum Sum of HTTP request durations.",
            "# TYPE ardupilot_http_request_duration_seconds_sum counter",
        ]
    )
    for (method, path), total in sorted(duration_sum.items()):
        lines.append(
            f'ardupilot_http_request_duration_seconds_sum{{method="{escape_label(method)}",path="{escape_label(path)}"}} {total:.6f}'
        )
    return "\n".join(lines) + "\n"


def _sha256_json_list(values: list[Any]) -> str:
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def _model_artifact_status() -> dict[str, Any]:
    """Inspect the configured model bundle without deserializing large weights."""
    model_dir = default_models_dir()
    required = {
        "classifier": model_dir / "classifier.joblib",
        "scaler": model_dir / "scaler.joblib",
        "feature_schema": model_dir / "feature_columns.json",
        "label_schema": model_dir / "label_columns.json",
        "manifest": model_dir / "manifest.json",
    }
    missing: list[str] = []
    for name, path in required.items():
        try:
            if not path.is_file() or path.stat().st_size <= 0:
                missing.append(name)
        except OSError:
            missing.append(name)
    result: dict[str, Any] = {
        "directory": str(model_dir),
        "configured": bool(os.environ.get("ARDUPILOT_DIAGNOSIS_MODEL_DIR")),
        "status": "missing" if missing else "unknown",
        "available": not missing,
        "missing": missing,
        "release_ready": False,
    }
    if missing:
        result["reason"] = "required model artifacts are missing or empty"
        return result
    try:
        feature_columns = json.loads(required["feature_schema"].read_text(encoding="utf-8"))
        label_columns = json.loads(required["label_schema"].read_text(encoding="utf-8"))
        manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))
        if not isinstance(feature_columns, list) or not isinstance(label_columns, list) or not isinstance(manifest, dict):
            raise ValueError("schema files must contain a JSON list and manifest must contain an object")
        feature_hash = _sha256_json_list(feature_columns)
        # Legacy manifests hash the runtime label list; v2 manifests hash the
        # trained list explicitly.  Check whichever contract is present.
        label_hash = _sha256_json_list(label_columns)
        manifest_feature_hash = str(manifest.get("feature_schema_hash", ""))
        trained_label_hash = str(manifest.get("trained_label_schema_hash", manifest.get("label_schema_hash", "")))
        schema_ok = bool(feature_columns) and bool(label_columns) and feature_hash == manifest_feature_hash and trained_label_hash in {label_hash, str(manifest.get("label_schema_hash", ""))}
        evaluation = manifest.get("evaluation", {}) if isinstance(manifest.get("evaluation", {}), dict) else {}
        macro_f1 = evaluation.get("macro_f1_log_test")
        holdout = evaluation.get("test_source_log_count")
        try:
            macro_f1 = float(macro_f1)
        except (TypeError, ValueError):
            macro_f1 = None
        try:
            holdout = int(holdout)
        except (TypeError, ValueError):
            holdout = None
        artifact_version = manifest.get("artifact_schema_version")
        model_kind = "versioned_candidate" if artifact_version is not None else "legacy_compatibility"
        release_ready = bool(schema_ok and macro_f1 is not None and macro_f1 >= 0.70 and holdout is not None and holdout >= 50)
        mtimes = [path.stat().st_mtime for path in required.values()]
        manifest_mtime = required["manifest"].stat().st_mtime
        stale_schema = any(path.stat().st_mtime > manifest_mtime + 1.0 for path in (required["classifier"], required["scaler"], required["feature_schema"], required["label_schema"]))
        if stale_schema:
            release_ready = False
        result.update(
            {
                "status": "stale" if schema_ok and stale_schema else ("ready" if schema_ok else "invalid"),
                "schema_valid": schema_ok,
                "artifact_schema_version": artifact_version,
                "model_kind": model_kind,
                "feature_count": len(feature_columns),
                "label_count": len(label_columns),
                "evaluation": {"macro_f1_log_test": macro_f1, "test_source_log_count": holdout},
                "release_ready": release_ready,
                "stale_schema": stale_schema,
                "artifact_mtime": max(mtimes),
            }
        )
        if not schema_ok:
            result["reason"] = "manifest and schema hashes do not match"
        elif stale_schema:
            result["reason"] = "one or more artifacts are newer than manifest.json"
        elif not release_ready:
            result["reason"] = "artifact is operational but has not passed the release gates"
        return result
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result.update({"status": "invalid", "available": False, "reason": f"invalid model metadata: {exc}"})
        return result


def _runtime_readiness() -> dict[str, Any]:
    """Return a cheap, machine-readable readiness snapshot for probes."""
    model = _model_artifact_status()
    try:
        capabilities = get_capability_registry()
        capability_status = "available" if capabilities else "empty"
    except Exception as exc:  # pragma: no cover - defensive startup boundary
        capability_status = "error"
        capabilities = []
        capability_error = str(exc)
    else:
        capability_error = None
    require_model = os.environ.get("ARDUPILOT_REQUIRE_ML_MODEL", "").strip().lower() in {"1", "true", "yes", "on"}
    require_release = os.environ.get("ARDUPILOT_REQUIRE_RELEASE_MODEL", "").strip().lower() in {"1", "true", "yes", "on"}
    ready = capability_status == "available" and (not require_model or model.get("available", False)) and (not require_release or model.get("release_ready", False))
    # Rules and quality checks remain usable when an ML bundle is absent or
    # legacy, but probes must make that reduced operating mode explicit.
    degraded_model = not model.get("available", False) or model.get("model_kind") == "legacy_compatibility" or not model.get("release_ready", False)
    status = "not_ready" if not ready else ("degraded" if degraded_model else "ready")
    result = {
        "schema_version": "health.v1",
        "status": status,
        "ready": ready,
        "version": APP_VERSION,
        "model": model,
        "capabilities": {"status": capability_status, "count": len(capabilities)},
        "requirements": {"ml_model": require_model, "release_model": require_release},
    }
    if capability_error:
        result["capabilities"]["error"] = capability_error
    return result

# Lazy singleton — instantiated once on first use so tests can monkeypatch RuleEngine freely
_rule_engine: RuleEngine | None = None


def _get_rule_engine() -> RuleEngine:
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = RuleEngine()
    return _rule_engine
MAX_UPLOAD_BYTES = 64 * 1024 * 1024
UPLOAD_CHUNK_SIZE = 1024 * 1024
MAX_JSON_BODY_BYTES = 8 * 1024 * 1024
MAX_COMPARE_FILES = 16
SUPPORTED_FLIGHT_EXTENSIONS = {".bin", ".log", ".ulg", ".ulog", ".tlog", ".bbl", ".bfl"}
WEB_DIR = Path(__file__).parent.absolute()


def _is_flight_log_filename(filename: str | None) -> bool:
    return bool(filename and Path(filename).suffix.lower() in SUPPORTED_FLIGHT_EXTENSIONS)


def _flight_log_temp_suffix(filename: str | None) -> str:
    """Preserve the adapter-significant suffix while using a safe fixed set."""
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix in SUPPORTED_FLIGHT_EXTENSIONS else ".bin"


class InvalidLogError(ValueError):
    """Raised when a file cannot be parsed into a usable flight log."""

    def __init__(self, message: str, quality_report: dict[str, Any] | None = None, code: ErrorCode = ErrorCode.PARSE_FAILED):
        super().__init__(message)
        self.quality_report = quality_report or {}
        self.code = code

def _cors_configuration() -> tuple[list[str], bool]:
    """Return explicitly configured CORS origins and credential policy.

    The dashboard is served by this same application, so it does not need
    cross-origin access by default.  In particular, ``*`` plus credentials is
    both rejected by browsers and an unsafe deployment default.  Operators
    who intentionally host a separate frontend can opt in with a comma
    separated ``ARDUPILOT_CORS_ORIGINS`` value.
    """
    raw = os.environ.get("ARDUPILOT_CORS_ORIGINS", "")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if origins == ["*"]:
        # Explicit public read access is still supported for integrations, but
        # never combine it with cookies/credentials.
        return ["*"], False
    origins = [origin for origin in origins if origin != "*"]
    return origins, bool(origins)


_cors_origins, _cors_allow_credentials = _cors_configuration()

@asynccontextmanager
async def lifespan(app):
    """Startup and shutdown lifecycle for the FastAPI application."""
    global streamer, _startup_runtime_state
    _startup_runtime_state = _runtime_readiness()
    if _startup_runtime_state.get("status") in {"not_ready", "degraded"}:
        LOGGER.warning(
            "Runtime readiness is %s: %s",
            _startup_runtime_state.get("status"),
            _startup_runtime_state.get("model", {}).get("reason"),
        )
    mavlink_conn = os.environ.get("MAVLINK_CONNECTION")
    if mavlink_conn:
        # Opening a serial/TCP connection is an external side effect.  Never
        # do it from an unauthenticated deployment; the CLI always provisions
        # this token before setting MAVLINK_CONNECTION.
        if not os.environ.get("MAVLINK_AUTH_TOKEN", "").strip():
            LOGGER.error(
                "MAVLINK_CONNECTION is configured but MAVLINK_AUTH_TOKEN is missing; live stream disabled"
            )
        else:
            streamer = MAVLinkStreamer(ws_manager, mavlink_conn)
            streamer.start()
    yield
    if streamer:
        streamer.stop()

app = FastAPI(title="ArduPilot Log Diagnosis API", lifespan=lifespan)


def _http_error_code(status_code: int) -> ErrorCode | str:
    return {
        401: ErrorCode.AUTH_REQUIRED,
        403: ErrorCode.AUTH_REQUIRED,
        404: ErrorCode.NOT_FOUND,
        413: ErrorCode.UPLOAD_TOO_LARGE,
        422: ErrorCode.PARAMETER_INPUT_INVALID,
        503: ErrorCode.SERVICE_UNAVAILABLE,
    }.get(status_code, f"HTTP_{status_code}")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Keep framework errors on the same machine-readable contract as routes."""
    detail = exc.detail if isinstance(exc.detail, str) else json.dumps(exc.detail, default=str)
    payload = error_payload(_http_error_code(exc.status_code), detail)
    # Preserve FastAPI's familiar ``detail`` key for existing clients while
    # exposing the stable error code used by CLI/integration consumers.
    payload["detail"] = exc.detail
    response = JSONResponse(status_code=exc.status_code, content=payload, headers=exc.headers)
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(RequestValidationError)
async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    fields = jsonable_encoder(exc.errors())
    payload = error_payload(
        ErrorCode.REQUEST_VALIDATION_FAILED,
        "Request validation failed.",
        fields=fields,
    )
    payload["detail"] = fields
    response = JSONResponse(status_code=422, content=payload)
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


@app.exception_handler(Exception)
async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    LOGGER.exception("Unhandled application exception", exc_info=exc)
    payload = error_payload(ErrorCode.INTERNAL_ERROR, "Internal server error. Check server logs for details.")
    response = JSONResponse(status_code=500, content=payload)
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    """Attach correlation/security headers and record bounded request metrics."""
    global _REQUEST_IN_FLIGHT
    request_id = _request_id(request.headers.get("x-request-id"))
    request.state.request_id = request_id
    started = time.perf_counter()
    with _METRICS_LOCK:
        _REQUEST_IN_FLIGHT += 1
    status_code = 500
    try:
        content_type = request.headers.get("content-type", "").lower()
        content_length = request.headers.get("content-length")
        try:
            declared_length = int(content_length) if content_length else None
        except ValueError:
            declared_length = None
        if (
            request.method in {"POST", "PUT", "PATCH"}
            and content_type.startswith("application/json")
            and declared_length is not None
            and declared_length > MAX_JSON_BODY_BYTES
        ):
            status_code = 413
            response = JSONResponse(
                status_code=status_code,
                content=error_payload(
                    ErrorCode.UPLOAD_TOO_LARGE,
                    f"JSON request exceeds {MAX_JSON_BODY_BYTES} bytes.",
                    max_bytes=MAX_JSON_BODY_BYTES,
                ),
            )
        else:
            response = await call_next(request)
        status_code = int(response.status_code)
        return response
    except Exception:
        LOGGER.exception(
            "Unhandled request error",
            extra={"request_id": request_id, "method": request.method, "path": request.url.path},
        )
        raise
    finally:
        duration = max(0.0, time.perf_counter() - started)
        metric_path = _metric_path(request)
        _record_request(request.method, metric_path, status_code, duration)
        LOGGER.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": metric_path,
                "status_code": status_code,
                "duration_ms": round(duration * 1000.0, 3),
            },
        )
        # ``response`` is intentionally looked up after the try block: an
        # exception is handled by FastAPI's server boundary and has no object
        # to decorate here.
        response_obj = locals().get("response")
        if response_obj is not None:
            response_obj.headers["X-Request-ID"] = request_id
            response_obj.headers.setdefault("X-Content-Type-Options", "nosniff")
            response_obj.headers.setdefault("X-Frame-Options", "DENY")
            response_obj.headers.setdefault("Referrer-Policy", "no-referrer")


@app.get("/healthz", response_model=dict)
@app.get("/api/health", response_model=dict)
async def health_check() -> dict[str, Any]:
    """Liveness probe; never deserializes model weights or touches a vehicle."""
    return {
        "schema_version": "health.v1",
        "status": "ok",
        "live": True,
        "ready": bool(_startup_runtime_state.get("ready", True)),
        "version": APP_VERSION,
    }


@app.get("/readyz", response_model=dict)
@app.get("/api/readiness", response_model=dict)
async def readiness_check() -> JSONResponse:
    """Readiness probe with explicit model/dependency state.

    A missing ML bundle is reported as degraded but still ready by default,
    because the deterministic rules and quality gates can safely serve users.
    Set ``ARDUPILOT_REQUIRE_ML_MODEL=1`` (and optionally
    ``ARDUPILOT_REQUIRE_RELEASE_MODEL=1``) when a deployment must refuse
    traffic until a signed/release-gated artifact is present.
    """
    state = _runtime_readiness()
    return JSONResponse(status_code=200 if state.get("ready") else 503, content=state)


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    """Expose process-local Prometheus metrics without request payloads."""
    return PlainTextResponse(_metrics_payload(), media_type="text/plain; version=0.0.4")

ws_manager = WebSocketManager()
streamer: MAVLinkStreamer | None = None


@app.get("/api/capabilities", response_model=dict)
async def capabilities() -> dict[str, Any]:
    return {"schema_version": "capabilities.v1", "capabilities": get_capability_registry()}


@app.get("/api/catalogue", response_model=dict)
async def catalogue_coverage() -> dict[str, Any]:
    return get_catalogue_manifest()


@app.get("/api/tools", response_model=dict)
async def tools_manifest() -> dict[str, Any]:
    return {"schema_version": "read-only-tools.v1", "tools": TOOL_DEFINITIONS}


@app.post("/api/tools/call", response_model=dict)
async def tools_call(payload: dict[str, Any]) -> dict[str, Any]:
    if len(json.dumps(payload, default=str)) > MAX_JSON_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content=error_payload(
                ErrorCode.UPLOAD_TOO_LARGE,
                f"Tool payload exceeds {MAX_JSON_BODY_BYTES} bytes.",
                max_bytes=MAX_JSON_BODY_BYTES,
            ),
        )
    name = str(payload.get("name", ""))
    result = dispatch_tool(name, payload.get("arguments", {}))
    return {"tool": name, "result": result, "read_only": True}


@app.post("/mcp", response_model=dict)
async def mcp_read_only_rpc(payload: dict[str, Any]) -> dict[str, Any]:
    """Minimal JSON-RPC-compatible read-only facade for MCP adapters."""
    if len(json.dumps(payload, default=str)) > MAX_JSON_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={
                "jsonrpc": "2.0",
                "id": payload.get("id"),
                "error": {"code": -32600, "message": "Request too large"},
                "read_only": True,
            },
        )
    request_id = payload.get("id")
    method = payload.get("method")
    if method == "tools/list":
        result = {"tools": TOOL_DEFINITIONS}
    elif method == "tools/call":
        params = payload.get("params", {}) or {}
        result = dispatch_tool(str(params.get("name", "")), params.get("arguments", {}))
    else:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32601, "message": "Method not found", "data": "read-only tools/list and tools/call are supported"}}
    return {"jsonrpc": "2.0", "id": request_id, "result": result, "read_only": True}


@app.post("/api/acceptance", response_model=dict)
async def acceptance(payload: dict[str, Any]) -> dict[str, Any]:
    return acceptance_report(payload.get("report", payload), payload.get("profile", {}))


@app.post("/api/baseline", response_model=dict)
async def baseline(payload: dict[str, Any]) -> dict[str, Any]:
    reports = payload.get("reports", [])
    return build_baseline(reports, label=str(payload.get("label", "known_good")))


@app.post("/api/maintenance", response_model=dict)
async def maintenance(payload: dict[str, Any]) -> dict[str, Any]:
    return maintenance_comparison(payload.get("before", {}), payload.get("after", {}))


@app.post("/api/context/weather", response_model=dict)
async def context_weather(payload: dict[str, Any]) -> dict[str, Any]:
    return weather_context(payload.get("parsed", {}), payload.get("weather", {}))


@app.post("/api/context/video-sync", response_model=dict)
async def context_video_sync(payload: dict[str, Any]) -> dict[str, Any]:
    return synchronize_video(payload.get("log_timestamps_us", []), payload.get("sync_points", []), video_time_base=str(payload.get("video_time_base", "seconds")))


@app.post("/api/context/video-overlay", response_model=dict)
async def context_video_overlay(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = payload.get("parsed", {})
    sync = payload.get("sync", {})
    result = build_video_overlay(parsed if isinstance(parsed, dict) else {}, sync if isinstance(sync, dict) else {})
    format_name = str(payload.get("format", "json")).lower().lstrip(".")
    if format_name in {"vtt", "srt"} and result.get("status") == "review_only":
        result["content"] = video_overlay_text(result, format_name=format_name)
        result["content_format"] = format_name
    return result


@app.post("/api/context/temporal", response_model=dict)
async def context_temporal(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = payload.get("parsed", {})
    diagnoses = payload.get("diagnoses", [])
    try:
        bins = int(payload.get("bins", 120))
    except (TypeError, ValueError):
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, "bins must be numeric."))
    return temporal_evidence(parsed if isinstance(parsed, dict) else {}, diagnoses if isinstance(diagnoses, list) else [], bins=bins)


@app.post("/api/checks/community", response_model=dict)
async def community_checks(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = payload.get("parsed", payload)
    return run_aynalike_checks(parsed if isinstance(parsed, dict) else {})


@app.post("/api/context/location-recurrence", response_model=dict)
async def context_location_recurrence(payload: dict[str, Any]) -> dict[str, Any]:
    reports = payload.get("reports", [])
    return location_recurrence(reports if isinstance(reports, list) else [], precision=payload.get("precision", 3))


@app.post("/api/track", response_model=dict)
async def track_export(payload: dict[str, Any]) -> dict[str, Any]:
    """Return offline track points plus GPX/KML text; never uploads coordinates."""
    source = payload.get("parsed", payload)
    points = track_points(source if isinstance(source, dict) else {})
    format_name = str(payload.get("format", "gpx")).lower().lstrip(".")
    if format_name not in {"gpx", "kml"}:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, "Track format must be gpx or kml."))
    points["format"] = format_name
    points["content"] = to_gpx(source, name=str(payload.get("name", "ArduPilot flight"))) if format_name == "gpx" else to_kml(source, name=str(payload.get("name", "ArduPilot flight")))
    points["privacy_notice"] = "Coordinates are exact in this export; scrub or round them before sharing."
    return points


@app.post("/api/methodic", response_model=dict)
async def methodic_review(payload: dict[str, Any]) -> dict[str, Any]:
    return review_methodic_step(payload.get("report", payload), str(payload.get("step", "")))


@app.post("/api/mission/validate", response_model=dict)
async def mission_validate(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate an operator-supplied mission without uploading or writing it."""
    return validate_mission(payload.get("mission", payload.get("waypoints", [])), geofence=payload.get("geofence"), rally_points=payload.get("rally_points"))


@app.post("/api/mission/compliance", response_model=dict)
async def mission_compliance(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare a supplied plan with parsed GPS telemetry, as a review aid only."""
    parsed = payload.get("parsed", {})
    try:
        tolerance_m = float(payload.get("tolerance_m", 30.0))
    except (TypeError, ValueError):
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, "tolerance_m must be numeric."))
    return mission_compliance_report(parsed if isinstance(parsed, dict) else {}, payload.get("mission", payload.get("waypoints", [])), tolerance_m=tolerance_m, geofence=payload.get("geofence"))


@app.post("/api/plot", response_model=dict)
async def plot_report(payload: dict[str, Any]) -> dict[str, Any]:
    return generate_plot(payload.get("report", payload), kind=str(payload.get("kind", "summary")))


@app.post("/api/graph-pack", response_model=dict)
async def graph_pack_report(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload.get("report", payload)
    parsed = payload.get("parsed", {})
    return generate_graph_pack(report if isinstance(report, dict) else {}, parsed=parsed if isinstance(parsed, dict) else {}, title=str(payload.get("title", "ArduPilot flight graph pack")))


@app.post("/api/derived-series", response_model=dict)
async def derived_series_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = payload.get("parsed", {})
        return derived_series(parsed if isinstance(parsed, dict) else {}, str(payload.get("expression", "")))
    except ValueError as exc:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, str(exc)))


@app.post("/api/artifacts", response_model=dict)
async def artifacts_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
    parsed = payload.get("parsed", payload)
    return artifact_manifest(parsed if isinstance(parsed, dict) else {})


def _fleet_store() -> FleetStore:
    return FleetStore(os.environ.get("ARDUPILOT_FLEET_DB", "fleet_reports.sqlite3"), retention_days=int(os.environ.get("ARDUPILOT_FLEET_RETENTION_DAYS", "0") or 0) or None)


def _request_token(request: Request | WebSocket | None, query_token: str | None) -> str | None:
    """Prefer an Authorization bearer token while retaining query compatibility.

    Query tokens are supported for older clients and the small local dashboard,
    but they can appear in proxy/access logs.  New integrations should send a
    bearer token instead.
    """
    query_value = query_token.strip() if isinstance(query_token, str) else None
    header_value = ""
    if request is not None:
        authorization = request.headers.get("authorization", "")
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer" and value.strip():
            header_value = value.strip()
    if query_value and header_value and not hmac.compare_digest(query_value, header_value):
        return None
    return header_value or query_value


def _check_fleet_token(token: str | None, request: Request | None = None) -> None:
    """Require a fleet token for HTTP requests; keep direct Python API calls compatible.

    Fleet reports may contain exact coordinates, aircraft identifiers, and
    maintenance notes.  An unset token therefore fails closed for network
    requests instead of silently exposing the local SQLite database.  Existing
    in-process callers (the documented CLI/library path) are intentionally
    unaffected when no token is configured because they do not cross a network
    boundary.
    """
    expected = os.environ.get("ARDUPILOT_FLEET_TOKEN", "").strip()
    if request is None and not expected:
        return
    if not expected:
        raise HTTPException(status_code=503, detail="Fleet auth token is not configured")
    provided = _request_token(request, token)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Fleet access token is invalid")


def _check_mavlink_token(token: str | None, request: Request | None = None) -> None:
    """Authenticate the HTTP live-stream controls without timing leaks."""
    expected = os.environ.get("MAVLINK_AUTH_TOKEN", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Server auth token not configured")
    provided = _request_token(request, token)
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.post("/api/fleet/reports", response_model=dict)
async def fleet_add_report(payload: dict[str, Any], token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    try:
        _check_fleet_token(token, request)
        store = _fleet_store()
        report_id = store.add_report(payload.get("report", payload), aircraft_id=str(payload.get("aircraft_id", "default")), filename=payload.get("filename"))
        return {"schema_version": "fleet-report.v1", "report_id": report_id, "aircraft_id": str(payload.get("aircraft_id", "default")), "stored_locally": True, "read_only_vehicle": True}
    except ValueError as exc:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, str(exc)))


@app.get("/api/fleet/reports", response_model=dict)
async def fleet_list_reports(aircraft_id: str | None = None, limit: int = 100, token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    _check_fleet_token(token, request)
    return {"schema_version": "fleet-reports.v1", "reports": _fleet_store().list_reports(aircraft_id=aircraft_id, limit=limit), "stored_locally": True}


@app.get("/api/fleet/trend", response_model=dict)
async def fleet_trend(aircraft_id: str = "default", limit: int = 100, token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    _check_fleet_token(token, request)
    return _fleet_store().trend(aircraft_id, limit=limit)


@app.get("/api/fleet/location-recurrence", response_model=dict)
async def fleet_location_recurrence(aircraft_id: str = "default", limit: int = 100, token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    _check_fleet_token(token, request)
    reports = [row["report"] for row in _fleet_store().list_reports(aircraft_id=aircraft_id, limit=limit)]
    result = location_recurrence(reports)
    result["aircraft_id"] = aircraft_id
    return result


@app.get("/api/fleet/search", response_model=dict)
async def fleet_search(aircraft_id: str | None = None, vehicle: str | None = None, firmware: str | None = None, filename: str | None = None, min_health: float | None = None, max_health: float | None = None, limit: int = 100, token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    _check_fleet_token(token, request)
    rows = _fleet_store().search_reports(aircraft_id=aircraft_id, vehicle=vehicle, firmware=firmware, filename=filename, min_health=min_health, max_health=max_health, limit=limit)
    return {"schema_version": "fleet-search.v1", "status": "reliable" if rows else "insufficient_data", "count": len(rows), "reports": rows, "stored_locally": True}


@app.post("/api/fleet/firmware-cohorts", response_model=dict)
async def fleet_firmware_cohorts(payload: dict[str, Any], token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    _check_fleet_token(token, request)
    return compare_firmware_cohorts(payload.get("reports", []))


@app.post("/api/fleet/maintenance", response_model=dict)
async def fleet_maintenance(payload: dict[str, Any], token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    try:
        _check_fleet_token(token, request)
        store = _fleet_store()
        event_id = store.add_maintenance(str(payload.get("aircraft_id", "default")), str(payload.get("event_type", "maintenance")), str(payload.get("note", "")), payload.get("event_time"))
        return {"schema_version": "maintenance-event.v1", "event_id": event_id, "stored_locally": True}
    except ValueError as exc:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, str(exc)))


@app.post("/api/fleet/alerts/preview", response_model=dict)
async def fleet_alert_preview(payload: dict[str, Any], token: str | None = Query(None), request: Request = None) -> dict[str, Any]:
    _check_fleet_token(token, request)
    result = evaluate_alerts(payload.get("report", payload), payload.get("rules", []))
    if payload.get("webhook_url") is not None:
        result["webhook"] = validate_webhook_url(str(payload.get("webhook_url")))
    return result


class ConnectRequest(BaseModel):
    connection_string: str

# FIX 3: Add token auth to /api/live/connect endpoint
# Prevents unauthorized callers from restarting the streamer or
# triggering arbitrary TCP/UDP/serial connections
@app.post("/api/live/connect")
async def connect_live_stream(req: ConnectRequest, token: str = Query(None), request: Request = None):
    _check_mavlink_token(token, request)
    global streamer
    if streamer and streamer.is_running:
        streamer.stop()
    streamer = MAVLinkStreamer(ws_manager, req.connection_string)
    streamer.start()
    return {"status": "started", "connection_string": req.connection_string}

# FIX 5: Add token auth to /api/live/stop endpoint
@app.post("/api/live/stop")
async def stop_live_stream(token: str = Query(None), request: Request = None):
    _check_mavlink_token(token, request)
    global streamer
    if streamer and streamer.is_running:
        streamer.stop()
        return {"status": "stopped"}
    return {"status": "already_stopped"}

@app.websocket("/api/live/stream")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    # FIX: Do not fall back to a predictable default token
    # If MAVLINK_AUTH_TOKEN is not set, reject all connections
    expected_token = os.environ.get("MAVLINK_AUTH_TOKEN", "").strip()
    provided = _request_token(websocket, token)
    if not expected_token or not provided or not hmac.compare_digest(provided, expected_token):
        await websocket.close(code=1008)
        return

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/", response_class=HTMLResponse)
async def get_index() -> str:
    index_path = WEB_DIR / "index.html"
    if index_path.exists():
        return index_path.read_text(encoding="utf-8")
    return "UI not found"


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_log(file: UploadFile = File(...)):
    if not _is_flight_log_filename(file.filename):
        return JSONResponse(status_code=400, content=error_payload(ErrorCode.UNSUPPORTED_EXTENSION, "Supported flight-log extensions are .BIN/.LOG, .ULG/.ULOG, .TLOG, .BBL, and .BFL."))

    fd, temp_path = tempfile.mkstemp(suffix=_flight_log_temp_suffix(file.filename))
    try:
        total_bytes = 0
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content=error_payload(ErrorCode.UPLOAD_TOO_LARGE, f"Uploaded file exceeds {MAX_UPLOAD_BYTES} bytes.", max_bytes=MAX_UPLOAD_BYTES),
                    )
                handle.write(chunk)

        detected = detect_file_format(temp_path)
        if detected.get("format") in {"text_log", "px4_ulog", "mavlink_tlog", "betaflight_bbl"} and not detected.get("supported", False):
            return JSONResponse(
                status_code=422,
                content={
                    "error": ErrorCode.UNSUPPORTED_FORMAT,
                    "format": detected.get("format"),
                    "format_name": detected.get("format_name"),
                    "supported_formats": supported_format_kinds(),
                    "reason": detected.get("unsupported_reason"),
                },
            )

        result = await asyncio.to_thread(_analyze_temp_log, temp_path, file.filename)
        return AnalysisResponse(**result)
    except InvalidLogError as exc:
        return JSONResponse(
            status_code=422,
            content={
                **error_payload(exc.code, str(exc)),
                "quality_report": exc.quality_report,
            },
        )
    except ValidationError as e:
        LOGGER.exception("Schema validation failed for model output")
        return JSONResponse(status_code=500, content=error_payload(ErrorCode.REPORT_EXPORT_FAILED, "Schema validation failed", details=e.errors()))
    except Exception:
        LOGGER.exception("Error during analysis")
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.PARSE_FAILED, "Analysis failed. Check server logs for details."),
        )
    finally:
        await file.close()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except PermissionError:
                pass


@app.post("/api/hardware", response_model=dict)
async def hardware_report(file: UploadFile = File(...)):
    """Return the standalone read-only hardware/configuration report."""
    if not _is_flight_log_filename(file.filename):
        return JSONResponse(status_code=400, content=error_payload(ErrorCode.UNSUPPORTED_EXTENSION, "Supported flight-log extensions are .BIN/.LOG, .ULG/.ULOG, .TLOG, .BBL, and .BFL."))
    fd, temp_path = tempfile.mkstemp(suffix=_flight_log_temp_suffix(file.filename))
    try:
        total_bytes = 0
        with os.fdopen(fd, "wb") as handle:
            while True:
                chunk = await file.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content=error_payload(ErrorCode.UPLOAD_TOO_LARGE, f"Uploaded file exceeds {MAX_UPLOAD_BYTES} bytes.", max_bytes=MAX_UPLOAD_BYTES),
                    )
                handle.write(chunk)
        detected = detect_file_format(temp_path)
        if detected.get("format") in {"text_log", "px4_ulog", "mavlink_tlog", "betaflight_bbl"} and not detected.get("supported", False):
            return JSONResponse(
                status_code=422,
                content={
                    "error": ErrorCode.UNSUPPORTED_FORMAT,
                    "format": detected.get("format"),
                    "format_name": detected.get("format_name"),
                    "supported_formats": supported_format_kinds(),
                    "reason": detected.get("unsupported_reason"),
                },
            )
        parsed = await asyncio.to_thread(LogParser(temp_path).parse)
        report = HardwareReportBuilder().build(parsed, parameter_mode="minimal")
        return report
    except Exception:
        LOGGER.exception("Error during hardware report")
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARSE_FAILED, "Hardware report failed for this log."))
    finally:
        await file.close()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except PermissionError:
                pass


async def _parameter_upload(upload: UploadFile) -> dict[str, Any]:
    if not upload.filename:
        raise ValueError("Parameter upload has no filename")
    content = await upload.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Uploaded file exceeds {MAX_UPLOAD_BYTES} bytes.")
    suffix = Path(upload.filename).suffix.lower()
    if suffix == ".bin":
        fd, temp_path = tempfile.mkstemp(suffix=".bin")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            if detect_file_format(temp_path)["format"] != "ardupilot_bin":
                raise ValueError("The uploaded .BIN does not have an ArduPilot DataFlash signature.")
            return LogParser(temp_path).parse().get("parameters", {})
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except PermissionError:
                    pass
    fd, temp_path = tempfile.mkstemp(suffix=suffix or ".param")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
        return load_parameter_file(temp_path)
    finally:
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except PermissionError:
                pass


@app.post("/api/param-diff", response_model=dict)
async def parameter_diff(before: UploadFile = File(...), after: UploadFile = File(...)):
    """Compare two read-only parameter snapshots or BIN embedded snapshots."""
    try:
        before_values = await _parameter_upload(before)
        after_values = await _parameter_upload(after)
        return diff_parameters(before_values, after_values)
    except ValueError as exc:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, str(exc)))
    finally:
        await before.close()
        await after.close()


@app.post("/api/param-validate", response_model=dict)
async def parameter_validate(file: UploadFile = File(...)):
    """Validate a parameter snapshot without proposing or writing changes."""
    try:
        values = await _parameter_upload(file)
        return validate_parameter_values(values)
    except ValueError as exc:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, str(exc)))
    finally:
        await file.close()


@app.get("/api/params", response_model=dict)
async def parameter_catalog(platform: str = "ardupilot", category: str | None = None) -> dict[str, Any]:
    return list_parameters(platform=platform, category=category)


@app.get("/api/params/search", response_model=dict)
async def parameter_search(query: str = "", platform: str = "ardupilot") -> dict[str, Any]:
    return search_parameters(query, platform=platform)


@app.post("/api/params/validate", response_model=dict)
async def parameter_value_validate(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        if isinstance(payload.get("catalog"), str):
            raise ValueError("Inline catalog data must be a list/object; server-side paths are not accepted.")
        catalog = load_catalog(payload["catalog"]) if "catalog" in payload else None
        return validate_parameter(str(payload.get("name", "")), payload.get("value"), platform=str(payload.get("platform", "ardupilot")), catalog=catalog)
    except (TypeError, ValueError) as exc:
        return JSONResponse(status_code=422, content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, str(exc)))


def _analyze_temp_log(temp_path: str, original_filename: str) -> dict[str, Any]:
    parser = LogParser(temp_path)
    parsed = parser.parse()

    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)

    metadata = features.get("_metadata", {})
    if not metadata.get("extraction_success", True):
        raise InvalidLogError(
            "The uploaded file could not be parsed as a usable supported flight log.",
            metadata.get("quality_report"),
        )

    engine = HybridEngine()
    windowing_info: dict[str, Any] = {
        "aggregation": "full_log",
        "candidate_count": 1,
        "source": "rule_only_or_ml_unavailable",
    }
    classifier = getattr(engine, "ml", None)
    if (
        getattr(classifier, "available", False)
        and classifier.get_inference_window_config().get("verified", False)
    ):
        ml_window_features, windowing_info = extract_ml_feature_candidates(
            parsed,
            pipeline,
            classifier.get_inference_window_config(),
            full_features=features,
        )
        diagnoses = engine.diagnose(features, window_features=ml_window_features)
    else:
        diagnoses = engine.diagnose(features)
        if getattr(classifier, "available", False):
            windowing_info["source"] = "legacy_model_window_contract_missing"
    explain_data = dict(getattr(engine, "last_explain_data", {}))
    explain_data["inference_window"] = windowing_info
    parameter_warnings = validate_parameters(
        parsed.get("parameters", {}),
        features,
        features.get("_metadata", {}).get("vehicle_type", "Unknown"),
    )

    # Never turn an empty result from a degraded/truncated/unsupported log
    # into a healthy decision.  The quality report is produced at extraction
    # time and is the canonical input-integrity signal for this gate.
    quality_report = features.get("_metadata", {}).get("quality_report", {})
    decision = (
        evaluate_decision(diagnoses, quality_report=quality_report)
        if quality_report
        else evaluate_decision(diagnoses)
    )
    explain_data["decision"] = decision

    time_series, timeline_events, gps_quality = _build_visualization_data(parsed, features)
    rule_diagnoses = _get_rule_engine().diagnose(features)
    detected_format = quality_report.get("input_format") if isinstance(quality_report, dict) else None
    if not detected_format:
        detected_format = parsed.get("metadata", {}).get("file_format")
    if rule_diagnoses:
        rule_output_only = rule_diagnoses[0]["failure_type"]
    elif not capability_supports_format("diagnosis", detected_format):
        rule_output_only = "unsupported_format"
    else:
        rule_output_only = (
            "nominal"
            if str(quality_report.get("overall_status", "RELIABLE")).upper() in {"RELIABLE", "GOOD"}
            else "uncertain"
        )
    hardware_report = HardwareReportBuilder().build(parsed, parameter_mode="minimal", diagnoses=diagnoses)
    health_score = calculate_health_score(diagnoses=diagnoses, quality_report=hardware_report.get("log_quality", {}))

    return {
        "schema_version": "analysis-response.v1",
        "metadata": {
            "filename": original_filename,
            "duration": features.get("_metadata", {}).get("duration_sec", 0),
            "vehicle": features.get("_metadata", {}).get("vehicle_type", "Unknown"),
            "file_format": parsed.get("metadata", {}).get("file_format"),
            "sha256": (parsed.get("metadata", {}).get("file_format", {}) or {}).get("sha256"),
        },
        "features": features,
        "diagnoses": diagnoses,
        # Keep the final policy decision at the response root as well as in
        # explain_data.  The root field is the stable machine-facing API
        # contract; explain_data remains the richer backwards-compatible
        # explanation envelope used by the dashboard.
        "decision": decision,
        "parameter_warnings": parameter_warnings,
        "explain_data": explain_data,
        "time_series": time_series,
        "timeline_events": timeline_events,
        "gps_quality": gps_quality,
        "rule_output_only": rule_output_only,
        "rule_output_diagnoses": rule_diagnoses,
        "hardware_report": hardware_report,
        "health_score": health_score,
    }


def _build_visualization_data(
    parsed: dict[str, Any], features: dict[str, Any]
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], dict[str, Any]]:
    time_series: dict[str, list[dict[str, Any]]] = {"gps": [], "vibe": []}
    gps_quality: dict[str, Any] = {
        "hdop": [],
        "sat_count": [],
        "fix_type": [],
        "avg_hdop": 0.0,
        "min_satellites": 0,
        "ttff_sec": None,
    }
    start_time = _find_start_time_us(parsed)

    vibe_msgs = parsed.get("messages", {}).get("VIBE", [])
    gps_msgs = parsed.get("messages", {}).get("GPS", [])

    vibe_times = [msg.get("TimeUS") for msg in vibe_msgs if msg.get("TimeUS") is not None]
    gps_times = [msg.get("TimeUS") for msg in gps_msgs if msg.get("TimeUS") is not None]
    if vibe_times and start_time is not None:
        log_end_time_s = (vibe_times[-1] - start_time) / 1e6
    elif gps_times and start_time is not None:
        log_end_time_s = (gps_times[-1] - start_time) / 1e6
    else:
        log_end_time_s = features.get("_metadata", {}).get("duration_sec", 0)

    step = max(1, len(vibe_msgs) // 500)
    for msg in vibe_msgs[::step]:
        t_us = msg.get("TimeUS")
        if t_us is None:
            continue
        if start_time is None:
            start_time = t_us
        time_series["vibe"].append(
            {
                "t": round((t_us - start_time) / 1e6, 2),
                "x": msg.get("VibeX", 0),
                "y": msg.get("VibeY", 0),
                "z": msg.get("VibeZ", 0),
            }
        )

    # --- Summary stats on FULL dataset for accuracy ---
    # Sampling would miss brief satellite drops or the exact first-fix moment.
    if gps_msgs:
        hdops = [m.get("HDop", 0.0) for m in gps_msgs]
        sats = [m.get("NSats", 0) for m in gps_msgs]
        gps_quality["avg_hdop"] = round(sum(hdops) / len(hdops), 2) if hdops else 0.0
        gps_quality["min_satellites"] = min(sats) if sats else 0

        for m in gps_msgs:
            if m.get("Status", 0) >= 3:
                t_us = m.get("TimeUS")
                if t_us is not None:
                    ref_time = start_time if start_time is not None else t_us
                    gps_quality["ttff_sec"] = round((t_us - ref_time) / 1e6, 2)
                break

    # --- Sampled loop: build time-series lists for display only ---
    step_gps = max(1, len(gps_msgs) // 500)

    for msg in gps_msgs[::step_gps]:
        lat = msg.get("Lat")
        lng = msg.get("Lng")
        alt = msg.get("Alt", 0)
        t_us = msg.get("TimeUS")

        hdop = msg.get("HDop", 0.0)
        nsats = msg.get("NSats", 0)
        status = msg.get("Status", 0)

        if t_us is not None:
            if start_time is None:
                start_time = t_us
            t_s = round((t_us - start_time) / 1e6, 2)

            gps_quality["hdop"].append({"t": t_s, "v": hdop})
            gps_quality["sat_count"].append({"t": t_s, "v": nsats})
            gps_quality["fix_type"].append({"t": t_s, "v": status})

        # DataFlash GPS coordinates are commonly integer 1e-7 degrees while
        # the ULog/TLog adapters normalize them to decimal degrees.  Keep the
        # visualization contract format-agnostic instead of shrinking generic
        # adapter coordinates to near-zero values.
        try:
            lat_value = float(lat)
            lng_value = float(lng)
        except (TypeError, ValueError):
            lat_value = lng_value = 0.0
        if abs(lat_value) > 90.0 or abs(lng_value) > 180.0:
            lat_value /= 1e7
            lng_value /= 1e7
        if lat_value and lng_value and t_us is not None:
            time_series["gps"].append(
                {
                    "t": round((t_us - start_time) / 1e6, 2),
                    "lat": lat_value,
                    "lng": lng_value,
                    "alt": alt,
                }
            )

    # Summary stats pre-calculated on full dataset above

    def get_gps_at(t_target: float) -> dict[str, Any] | None:
        if not time_series["gps"]:
            return None
        return min(time_series["gps"], key=lambda point: abs(point["t"] - t_target))

    timeline_events: list[dict[str, Any]] = []
    err_label_map = {
        3: ("Compass Error", "critical"),
        5: ("Radio Failsafe", "critical"),
        6: ("Battery Failsafe", "critical"),
        11: ("GPS Glitch", "warning"),
        12: ("Crash Detected", "crash"),
        16: ("EKF Check Failed", "critical"),
        17: ("EKF Failsafe", "crash"),
        25: ("Thrust Loss", "critical"),
        29: ("Vibration Failsafe", "critical"),
    }
    for err in parsed.get("errors", []):
        t_us = err.get("time_us")
        if t_us is None or start_time is None:
            continue
        t_s = round((t_us - start_time) / 1e6, 2)
        subsys = err.get("subsystem", 0)
        label, severity = err_label_map.get(
            subsys, (err.get("subsystem_name", "Error"), "warning")
        )
        timeline_events.append(
            {
                "t_sec": t_s,
                "type": "error",
                "label": label,
                "severity": severity,
                "gps": get_gps_at(t_s),
            }
        )

    for mc in parsed.get("mode_changes", []):
        t_us = mc.get("time_us")
        if t_us is None or start_time is None:
            continue
        t_s = round((t_us - start_time) / 1e6, 2)
        timeline_events.append(
            {
                "t_sec": t_s,
                "type": "mode",
                "label": f"Mode -> {mc.get('mode_name', 'Unknown')}",
                "severity": "warning" if mc.get("reason", 0) != 0 else "normal",
                "gps": get_gps_at(t_s),
            }
        )

    for msg in vibe_msgs:
        vibe_z = msg.get("VibeZ", 0)
        t_us = msg.get("TimeUS")
        if vibe_z > 30 and start_time is not None and t_us is not None:
            t_s = round((t_us - start_time) / 1e6, 2)
            timeline_events.append(
                {
                    "t_sec": t_s,
                    "type": "vibe_spike",
                    "label": f"Vibration Spike ({vibe_z:.1f} m/s^2)",
                    "severity": "warning",
                    "gps": get_gps_at(t_s),
                }
            )
            break

    timeline_events.append(
        {
            "t_sec": round(log_end_time_s, 2),
            "type": "crash",
            "label": "Log End / Impact",
            "severity": "crash",
            "gps": time_series["gps"][-1] if time_series["gps"] else None,
        }
    )
    timeline_events.sort(key=lambda event: event["t_sec"])

    return time_series, timeline_events, gps_quality


def _find_start_time_us(parsed: dict[str, Any]) -> int | None:
    """Return the earliest timestamp (us) seen across all message streams.

    Using the first-seen value from a single stream can produce negative time
    offsets when GPS messages begin earlier than VIBE messages (or vice versa).
    Taking the true minimum across every stream prevents that.
    """
    candidates: list[int] = []

    message_groups = parsed.get("messages", {})
    for message_type in ("VIBE", "GPS"):
        for msg in message_groups.get(message_type, []):
            t_us = msg.get("TimeUS")
            if t_us is not None:
                candidates.append(t_us)
                break  # only the first timestamp from each stream is needed

    for collection_name in ("errors", "mode_changes", "events"):
        for item in parsed.get(collection_name, []):
            t_us = item.get("time_us")
            if t_us is not None:
                candidates.append(t_us)
                break

    return min(candidates) if candidates else None


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        assistant = ChatAssistant()
        response_data = assistant.ask(request.question, request.analysis_result)
        return ChatResponse(
            question=response_data["question"],
            answer=response_data["answer"],
            confidence=response_data["confidence"],
            sources=response_data.get("sources", []),
            follow_up=response_data.get("follow_up", [])
        )
    except Exception:
        LOGGER.exception("Error during chat")
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.ANALYSIS_FAILED, "Chat failed. Check server logs for details.")
        )


@app.post("/api/compare", response_model=dict)
async def compare_flights(files: list[UploadFile] = File(...)):
    if len(files) < 2:
        return JSONResponse(
            status_code=400,
            content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, "At least 2 files required for comparison")
        )
    if len(files) > MAX_COMPARE_FILES:
        return JSONResponse(
            status_code=413,
            content=error_payload(
                ErrorCode.PARAMETER_INPUT_INVALID,
                f"Comparison accepts at most {MAX_COMPARE_FILES} files.",
                max_files=MAX_COMPARE_FILES,
            ),
        )
    try:
        analysis_results = []
        for file in files:
            if not _is_flight_log_filename(file.filename):
                continue
            fd, temp_path = tempfile.mkstemp(suffix=_flight_log_temp_suffix(file.filename))
            try:
                with os.fdopen(fd, "wb") as f:
                    total_bytes = 0
                    while True:
                        chunk = await file.read(UPLOAD_CHUNK_SIZE)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > MAX_UPLOAD_BYTES:
                            return JSONResponse(status_code=413, content=error_payload(ErrorCode.UPLOAD_TOO_LARGE, f"Uploaded file exceeds {MAX_UPLOAD_BYTES} bytes.", max_bytes=MAX_UPLOAD_BYTES))
                        f.write(chunk)
                detected = detect_file_format(temp_path)
                if detected.get("format") in {"text_log", "px4_ulog", "mavlink_tlog", "betaflight_bbl"} and not detected.get("supported", False):
                    continue
                result = _analyze_temp_log(temp_path, file.filename)
                analysis_results.append(result)
            finally:
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
        if len(analysis_results) < 2:
            return JSONResponse(
                status_code=400,
                content=error_payload(ErrorCode.PARAMETER_INPUT_INVALID, "Need at least 2 valid supported flight-log files")
            )
        analyzer = TrendAnalyzer()
        trend_report = analyzer.compare_flights(analysis_results)
        return trend_report
    except Exception:
        LOGGER.exception("Error during comparison")
        return JSONResponse(
            status_code=500,
            content=error_payload(ErrorCode.ANALYSIS_FAILED, "Comparison failed. Check server logs for details.")
        )
