"""Trend analyzer for multi-flight comparison and degradation detection."""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime


@dataclass
class FlightMetrics:
    """Key metrics extracted from a single flight analysis."""
    filename: str
    duration: float
    vibe_x_mean: float
    vibe_y_mean: float
    vibe_z_mean: float
    vibe_clip_total: float
    mag_field_range: float
    bat_volt_min: float
    bat_curr_max: float
    ekf_vel_var_max: float
    ekf_pos_var_max: float
    motor_spread_max: float
    gps_hdop_max: float
    primary_diagnosis: str
    diagnosis_confidence: float
    timestamp: str
    vehicle_type: str = "Unknown"
    firmware_version: str = "Unknown"
    source_sha256: str = ""
    quality_status: str = "UNKNOWN"
    
    @classmethod
    def from_analysis_result(cls, result: Dict[str, Any], filename: str) -> "FlightMetrics":
        """Create FlightMetrics from analysis JSON result."""
        features = result.get("features", {})
        diagnoses = result.get("diagnoses", [])
        
        # Get primary diagnosis
        primary_diag = diagnoses[0] if diagnoses else {"failure_type": "unknown", "confidence": 0.0}
        
        metadata = result.get("metadata", {}) or {}
        hardware = result.get("hardware_report", {}) or {}
        hardware_meta = hardware.get("metadata", {}) if isinstance(hardware, dict) else {}
        file_info = hardware.get("file", {}) if isinstance(hardware, dict) else {}
        log_path = metadata.get("log_file") or metadata.get("filename") or filename
        try:
            timestamp = datetime.fromtimestamp(Path(str(log_path)).stat().st_mtime).isoformat()
        except (OSError, ValueError, TypeError):
            timestamp = str(metadata.get("timestamp") or filename)
        return cls(
            filename=filename,
            duration=metadata.get("duration", metadata.get("duration_sec", 0.0)),
            vibe_x_mean=features.get("vibe_x_mean", 0.0),
            vibe_y_mean=features.get("vibe_y_mean", 0.0),
            vibe_z_mean=features.get("vibe_z_mean", 0.0),
            vibe_clip_total=features.get("vibe_clip_total", 0.0),
            mag_field_range=features.get("mag_field_range", 0.0),
            bat_volt_min=features.get("bat_volt_min", 0.0),
            bat_curr_max=features.get("bat_curr_max", 0.0),
            ekf_vel_var_max=features.get("ekf_vel_var_max", 0.0),
            ekf_pos_var_max=features.get("ekf_pos_var_max", 0.0),
            motor_spread_max=features.get("motor_spread_max", 0.0),
            gps_hdop_max=features.get("gps_hdop_max", 0.0),
            primary_diagnosis=primary_diag.get("failure_type", "unknown"),
            diagnosis_confidence=primary_diag.get("confidence", 0.0),
            timestamp=timestamp,
            vehicle_type=metadata.get("vehicle_type", metadata.get("vehicle", hardware_meta.get("vehicle_type", "Unknown"))),
            firmware_version=metadata.get("firmware", hardware_meta.get("firmware_version", "Unknown")),
            source_sha256=file_info.get("sha256", ""),
            quality_status=(metadata.get("quality_report", {}) or {}).get("overall_status", "UNKNOWN"),
        )


@dataclass
class TrendInsight:
    """Actionable insight from trend analysis."""
    metric: str
    change_percent: float
    direction: str  # "increased", "decreased", "stable"
    severity: str  # "critical", "warning", "info"
    message: str
    recommendation: str


class TrendAnalyzer:
    """Analyzes trends across multiple flights to detect degradation."""
    
    # Thresholds for degradation detection
    DEGRADATION_THRESHOLDS = {
        "vibe_clip_total": {"warning": 20.0, "critical": 50.0},
        "vibe_z_mean": {"warning": 30.0, "critical": 60.0},
        "ekf_vel_var_max": {"warning": 25.0, "critical": 50.0},
        "ekf_pos_var_max": {"warning": 25.0, "critical": 50.0},
        # Thresholds are positive magnitudes.  Direction is handled explicitly
        # below because only a *drop* in minimum voltage is degradation.
        "bat_volt_min": {"warning": 10.0, "critical": 20.0},
        "motor_spread_max": {"warning": 15.0, "critical": 30.0},
    }
    
    def __init__(self, cache_dir: Optional[Path] = None):
        """Initialize trend analyzer with optional cache directory."""
        self.cache_dir = cache_dir or Path.home() / ".ardupilot_diagnosis" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "analysis_cache.json"
        self._cache = self._load_cache()
    
    def _load_cache(self) -> Dict[str, Any]:
        """Load analysis cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {}
        return {}
    
    def _save_cache(self):
        """Save analysis cache to disk."""
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except IOError as e:
            print(f"Warning: Could not save cache: {e}")
    
    def _compute_file_hash(self, filepath: Path) -> str:
        """Compute SHA256 hash of file for cache key."""
        hasher = hashlib.sha256()
        with open(filepath, 'rb') as f:
            while chunk := f.read(8192):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]
    
    def cache_result(self, filepath: Path, result: Dict[str, Any]):
        """Cache analysis result for future comparison."""
        file_hash = self._compute_file_hash(filepath)
        self._cache[file_hash] = {
            "filepath": str(filepath),
            "filename": filepath.name,
            "result": result,
            "cached_at": datetime.now().isoformat()
        }
        self._save_cache()
    
    def get_cached_result(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Retrieve cached analysis result if available."""
        file_hash = self._compute_file_hash(filepath)
        cached = self._cache.get(file_hash)
        if cached:
            return cached.get("result")
        return None
    
    def analyze_trend(self, flights: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analyze trends across multiple flights.
        
        Args:
            flights: List of analysis results with filenames
            
        Returns:
            Dictionary containing trend analysis, metrics comparison, and insights
        """
        if len(flights) < 2:
            return {
                "error": "Need at least 2 flights for trend analysis",
                "flights_analyzed": len(flights)
            }
        
        # Extract metrics from each flight
        metrics_list = []
        for flight in flights:
            if isinstance(flight, dict) and "features" in flight:
                metrics = FlightMetrics.from_analysis_result(
                    flight, 
                    flight.get("metadata", {}).get("filename", "unknown")
                )
                metrics_list.append(metrics)
            elif isinstance(flight, FlightMetrics):
                metrics_list.append(flight)
        
        if len(metrics_list) < 2:
            return {
                "error": "Could not extract metrics from flights",
                "flights_analyzed": len(metrics_list)
            }
        
        # Sort by timestamp (oldest first)
        metrics_list.sort(key=lambda m: m.timestamp)
        
        # Calculate trends
        trends = self._calculate_trends(metrics_list)
        insights = self._generate_insights(trends, flight_count=len(metrics_list))
        
        configurations = sorted({(m.vehicle_type, m.firmware_version) for m in metrics_list})
        comparable = len(configurations) <= 1
        return {
            "schema_version": "trend-report.v2",
            "flights_analyzed": len(metrics_list),
            "flight_order": [m.filename for m in metrics_list],
            "metrics_timeline": [asdict(m) for m in metrics_list],
            "comparison_quality": {
                "comparable": comparable,
                "configurations": [
                    {"vehicle_type": vehicle, "firmware_version": firmware}
                    for vehicle, firmware in configurations
                ],
                "warning": None if comparable else "Flights use different vehicle or firmware identities; interpret trends as provisional.",
            },
            "trends": trends,
            "insights": [asdict(i) for i in insights],
            "summary": self._generate_summary(insights, metrics_list)
        }
    
    def _calculate_trends(self, metrics_list: List[FlightMetrics]) -> Dict[str, Any]:
        """Calculate percentage changes between first and last flight."""
        first = metrics_list[0]
        last = metrics_list[-1]
        
        trends = {}
        numeric_fields = [
            "vibe_x_mean", "vibe_y_mean", "vibe_z_mean", "vibe_clip_total",
            "mag_field_range", "bat_volt_min", "bat_curr_max",
            "ekf_vel_var_max", "ekf_pos_var_max", "motor_spread_max", "gps_hdop_max"
        ]
        
        for field in numeric_fields:
            first_val = getattr(first, field, 0.0)
            last_val = getattr(last, field, 0.0)
            
            if first_val != 0:
                change_pct = ((last_val - first_val) / abs(first_val)) * 100
            else:
                change_pct = 0.0 if last_val == 0 else 100.0
            
            trends[field] = {
                "first_value": first_val,
                "last_value": last_val,
                "change_percent": round(change_pct, 2),
                "direction": "increased" if change_pct > 5 else ("decreased" if change_pct < -5 else "stable")
            }
        
        # Add diagnosis trend
        trends["diagnosis"] = {
            "first": first.primary_diagnosis,
            "last": last.primary_diagnosis,
            "confidence_first": first.diagnosis_confidence,
            "confidence_last": last.diagnosis_confidence,
            "changed": first.primary_diagnosis != last.primary_diagnosis
        }
        
        return trends
    
    def _generate_insights(self, trends: Dict[str, Any], flight_count: int | None = None) -> List[TrendInsight]:
        """Generate actionable insights from trends."""
        insights = []
        
        for metric, trend_data in trends.items():
            if metric == "diagnosis" or not isinstance(trend_data, dict):
                continue
            
            change_pct = trend_data.get("change_percent", 0)
            thresholds = self.DEGRADATION_THRESHOLDS.get(metric, {})
            
            # Determine severity only in the direction that represents
            # degradation.  A large improvement must never generate a
            # CRITICAL alert merely because its percentage is large.
            harmful_change = -change_pct if metric == "bat_volt_min" else change_pct
            severity = "info"
            if harmful_change >= thresholds.get("critical", 100):
                severity = "critical"
            elif harmful_change >= thresholds.get("warning", 100):
                severity = "warning"
            
            if severity == "info" and abs(change_pct) < 10:
                continue  # Skip minor changes
            
            # Generate message
            direction = "increased" if change_pct > 0 else "decreased"
            metric_name = metric.replace("_", " ").upper()
            
            message = f"{metric_name} {direction} by {abs(change_pct):.1f}% over {flight_count or len(trends)} flights"
            
            # Generate recommendation
            recommendation = self._get_recommendation(metric, change_pct, severity)
            
            insights.append(TrendInsight(
                metric=metric,
                change_percent=change_pct,
                direction=direction,
                severity=severity,
                message=message,
                recommendation=recommendation
            ))
        
        # Sort by severity
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        insights.sort(key=lambda i: (severity_order.get(i.severity, 3), abs(i.change_percent)))
        
        return insights
    
    def _get_recommendation(self, metric: str, change_pct: float, severity: str) -> str:
        """Generate specific recommendation based on metric and change."""
        recommendations = {
            "vibe_clip_total": lambda: "Inspect propellers for damage, check motor mounts, verify frame integrity." if change_pct > 0 else "Vibration levels improving - continue monitoring.",
            "vibe_z_mean": lambda: "Check propeller balance and motor bearings. Consider softer mounting." if change_pct > 0 else "Vibration trending down - good maintenance.",
            "ekf_vel_var_max": lambda: "Investigate sensor fusion issues. Check IMU and GPS data quality." if change_pct > 0 else "EKF performance stable or improving.",
            "ekf_pos_var_max": lambda: "Review GPS and compass data. May indicate sensor degradation." if change_pct > 0 else "Position estimate quality acceptable.",
            "bat_volt_min": lambda: "Battery showing increased sag. Check cell health and connections." if change_pct < 0 else "Battery performance stable.",
            "motor_spread_max": lambda: "Motor imbalance detected. Check ESC calibration and propeller condition." if change_pct > 0 else "Motor balance within acceptable range.",
            "mag_field_range": lambda: "Compass interference increasing. Check for new EMI sources." if change_pct > 0 else "Compass readings stable.",
        }
        
        return recommendations.get(metric, lambda: "Monitor this parameter in future flights.")()
    
    def _generate_summary(self, insights: List[TrendInsight], metrics_list: List[FlightMetrics]) -> str:
        """Generate human-readable summary of trend analysis."""
        critical_count = sum(1 for i in insights if i.severity == "critical")
        warning_count = sum(1 for i in insights if i.severity == "warning")
        
        if critical_count > 0:
            status = "⚠️ CRITICAL ISSUES DETECTED"
        elif warning_count > 0:
            status = "⚡ WARNING: Degradation detected"
        else:
            status = "✅ All trends within normal range"
        
        summary_parts = [status]
        
        # Add top insight
        if insights:
            top_insight = insights[0]
            summary_parts.append(f"\nTop concern: {top_insight.message}")
            summary_parts.append(f"\nRecommendation: {top_insight.recommendation}")
        
        # Add flight count
        summary_parts.append(f"\n\nAnalyzed {len(metrics_list)} flights from {metrics_list[0].filename} to {metrics_list[-1].filename}")
        
        return "".join(summary_parts)
    
    def compare_flights(self, analysis_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare multiple flight analysis results.
        
        Args:
            analysis_results: List of analysis JSON results from different flights
            
        Returns:
            Comparison report with trends and insights
        """
        return self.analyze_trend(analysis_results)
