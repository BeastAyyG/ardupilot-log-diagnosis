"""Rule-based chat assistant for log analysis Q&A."""

import re
from typing import Dict, List, Any, Optional, Tuple


class ChatAssistant:
    """
    Lightweight rule-based chat assistant for answering questions about log analysis.
    
    Supports questions like:
    - "Is motor 3 vibration normal?"
    - "Why did EKF spike at 47s?"
    - "What caused the crash?"
    - "Show me the timeline"
    """
    
    def __init__(self):
        """Initialize the chat assistant with pattern-response mappings."""
        self.patterns = self._build_patterns()
    
    def _build_patterns(self) -> List[Tuple[re.Pattern, callable]]:
        """Build regex patterns and response generators."""
        return [
            # Vibration questions
            (
                re.compile(r'(vibration|vibe)[\s\w]*(normal|high|bad|issue|problem)?', re.IGNORECASE),
                self._answer_vibration_question
            ),
            # EKF questions
            (
                re.compile(r'ekf[\s\w]*(spike|fail|variance|issue|problem)?', re.IGNORECASE),
                self._answer_ekf_question
            ),
            # Motor questions
            (
                re.compile(r'motor[\s\w]*(\d+)?[\s\w]*(imbalance|issue|problem|normal)?', re.IGNORECASE),
                self._answer_motor_question
            ),
            # Compass questions
            (
                re.compile(r'(compass|mag)[\s\w]*(interference|issue|problem|normal)?', re.IGNORECASE),
                self._answer_compass_question
            ),
            # GPS questions
            (
                re.compile(r'gps[\s\w]*(quality|issue|problem|signal|lock)?', re.IGNORECASE),
                self._answer_gps_question
            ),
            # Battery/Power questions
            (
                re.compile(r'(battery|power|voltage)[\s\w]*(sag|issue|problem|normal)?', re.IGNORECASE),
                self._answer_power_question
            ),
            # Root cause questions
            (
                re.compile(r'(what caused|why|root cause|crash reason)', re.IGNORECASE),
                self._answer_root_cause_question
            ),
            # Timeline questions
            (
                re.compile(r'(timeline|when|sequence|order of events)', re.IGNORECASE),
                self._answer_timeline_question
            ),
            # Confidence questions
            (
                re.compile(r'(how sure|confidence|certain|probability)', re.IGNORECASE),
                self._answer_confidence_question
            ),
            # Recommendation questions
            (
                re.compile(r'(what should|recommend|fix|repair|check|inspect)', re.IGNORECASE),
                self._answer_recommendation_question
            ),
            # Summary questions
            (
                re.compile(r'(summary|overview|tell me about|what happened)', re.IGNORECASE),
                self._answer_summary_question
            ),
        ]
    
    def ask(self, question: str, analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a user question and generate a response.
        
        Args:
            question: User's natural language question
            analysis_result: JSON analysis result from diagnosis engine
            
        Returns:
            Dictionary with answer, confidence, and optional follow-up suggestions
        """
        # Try to match question to patterns
        for pattern, handler in self.patterns:
            if pattern.search(question):
                answer = handler(question, analysis_result)
                if answer:
                    answer = self._ground_answer(answer, analysis_result)
                    return {
                        "question": question,
                        "answer": answer["text"],
                        "confidence": answer.get("confidence", 0.8),
                        "sources": answer.get("sources", []),
                        "follow_up": answer.get("follow_up", [])
                    }
        
        # No pattern matched - provide generic response
        return {
            "question": question,
            "answer": self._generic_response(analysis_result),
            "confidence": 0.5,
            "sources": [],
            "follow_up": [
                "Try asking about vibration, EKF, motors, compass, GPS, or battery",
                "Ask 'What caused the crash?' for root cause analysis"
            ]
        }

    @staticmethod
    def _quality_report(analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """Return the canonical quality report regardless of report shape."""
        hardware = analysis_result.get("hardware_report", {}) or {}
        features = analysis_result.get("features", {})
        metadata = analysis_result.get("metadata", {})
        candidates = [
            hardware.get("log_quality") if isinstance(hardware, dict) else None,
            (features.get("_metadata", {}) or {}).get("quality_report") if isinstance(features, dict) else None,
            metadata.get("quality_report") if isinstance(metadata, dict) else None,
            analysis_result.get("log_quality"),
        ]
        for quality in candidates:
            if isinstance(quality, dict) and quality:
                return quality
        return {}

    @classmethod
    def _capability_status(cls, analysis_result: Dict[str, Any], name: str) -> tuple[str, dict[str, Any]]:
        quality = cls._quality_report(analysis_result)
        capabilities = quality.get("capabilities", {}) if isinstance(quality, dict) else {}
        item = capabilities.get(name, {}) if isinstance(capabilities, dict) else {}
        return str(item.get("status", "UNKNOWN")).upper(), item if isinstance(item, dict) else {}

    @classmethod
    def _ground_answer(cls, answer: Dict[str, Any], analysis_result: Dict[str, Any]) -> Dict[str, Any]:
        """Cap confidence and cite only evidence present in the canonical result.

        Missing telemetry is not evidence of a normal subsystem.  Keep the
        conversational answer useful, but make parser quality and capability
        limits explicit so chat cannot clear a flight from zero-filled fields.
        """
        features = analysis_result.get("features", {})
        quality = cls._quality_report(analysis_result)
        sources = list(answer.get("sources", []))
        sources.append(f"canonical analysis {analysis_result.get('schema_version', 'analysis result')}")
        quality_status = str(quality.get("overall_status", "")).upper() if isinstance(quality, dict) else ""
        if quality_status in {"UNSUPPORTED", "INSUFFICIENT_DATA", "INVALID", "TRUNCATED", "UNKNOWN"}:
            answer["confidence"] = min(float(answer.get("confidence", 0.0)), 0.25)
            answer["text"] += (
                f" Input quality is {quality_status or 'UNKNOWN'}; this is a provisional review aid, "
                "not a clearance or a complete diagnosis."
            )
            sources.append("quality_report.integrity")
        elif quality_status not in {"", "RELIABLE", "GOOD"}:
            answer["confidence"] = min(float(answer.get("confidence", 0.0)), 0.55)
            answer["text"] += " Data quality is degraded, so this answer is confidence-capped and needs human review."
            sources.append("quality_report.integrity")
        if not features:
            answer["confidence"] = 0.1
            answer["text"] = "The canonical result does not contain the telemetry features required to answer this question; no diagnosis is inferred."
        answer["sources"] = sources
        return answer
    
    def _answer_vibration_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer vibration-related questions."""
        status, capability = self._capability_status(result, "vibration_analysis")
        if status in {"UNSUPPORTED", "UNKNOWN"}:
            return {
                "text": "Vibration cannot be assessed because VIBE/IMU telemetry is missing or unsupported in this log.",
                "confidence": 0.1,
                "sources": ["quality_report.capabilities.vibration_analysis"],
                "follow_up": [capability.get("recommendation", "Capture VIBE and IMU telemetry on the next flight.")],
            }
        features = result.get("features", {})
        vibe_z = features.get("vibe_z_mean", 0)
        vibe_clip = features.get("vibe_clip_total", 0)
        
        threshold = 30.0  # m/s²
        clip_threshold = 100
        
        is_high = vibe_z > threshold or vibe_clip > clip_threshold
        
        text = "Vibration analysis: "
        if is_high:
            text += f"Vibration levels are HIGH. VibeZ mean: {vibe_z:.2f} m/s² (threshold: {threshold}), "
            text += f"Total clips: {vibe_clip:.0f} (threshold: {clip_threshold}). "
            text += "This indicates IMU clipping - the flight controller was flying blind during high-vibration periods."
        else:
            text += f"Vibration levels are NORMAL. VibeZ mean: {vibe_z:.2f} m/s², Total clips: {vibe_clip:.0f}. "
            text += "Within acceptable limits."
        
        return {
            "text": text,
            "confidence": 0.95,
            "sources": ["VIBE message data", "Feature extraction pipeline"],
            "follow_up": ["Check propeller balance", "Inspect motor mounts"]
        }
    
    def _answer_ekf_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer EKF-related questions."""
        status, capability = self._capability_status(result, "ekf_state_estimation")
        if status in {"UNSUPPORTED", "UNKNOWN"}:
            return {
                "text": "EKF health cannot be assessed because XKF4/NKF4 variance telemetry is missing or unsupported in this log.",
                "confidence": 0.1,
                "sources": ["quality_report.capabilities.ekf_state_estimation"],
                "follow_up": [capability.get("recommendation", "Enable EKF variance logging on the next flight.")],
            }
        features = result.get("features", {})
        ekf_vel_var = features.get("ekf_vel_var_max", 0)
        ekf_pos_var = features.get("ekf_pos_var_max", 0)
        
        # Check diagnoses for EKF failure
        diagnoses = result.get("diagnoses", [])
        ekf_diagnosis = next((d for d in diagnoses if d.get("failure_type") == "ekf_failure"), None)
        
        text = "EKF status: "
        if ekf_diagnosis:
            confidence = ekf_diagnosis.get("confidence", 0) * 100
            text += f"EKF FAILURE detected with {confidence:.0f}% confidence. "
            text += f"Max velocity variance: {ekf_vel_var:.2f}, position variance: {ekf_pos_var:.2f}. "
            text += "Note: EKF failures are usually SYMPTOMS, not root causes. Check upstream sensors (IMU, GPS, compass)."
        elif ekf_vel_var > 1.0 or ekf_pos_var > 1.0:
            text += f"EKF variances elevated but not critical. Velocity var: {ekf_vel_var:.2f}, Position var: {ekf_pos_var:.2f}. "
            text += "Monitor for degradation."
        else:
            text += f"EKF variances nominal. Velocity var: {ekf_vel_var:.2f}, Position var: {ekf_pos_var:.2f}."
        
        return {
            "text": text,
            "confidence": 0.9,
            "sources": ["EKF message data", "Hybrid diagnosis engine"],
            "follow_up": ["Check what caused EKF divergence", "Review sensor fusion timeline"]
        }
    
    def _answer_motor_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer motor-related questions."""
        status, capability = self._capability_status(result, "motor_balance_mechanics")
        if status in {"UNSUPPORTED", "UNKNOWN"}:
            return {
                "text": "Motor balance cannot be assessed because RCOU/MOT or attitude telemetry is missing or unsupported in this log.",
                "confidence": 0.1,
                "sources": ["quality_report.capabilities.motor_balance_mechanics"],
                "follow_up": [capability.get("recommendation", "Capture RCOU/MOT and ATT telemetry on the next flight.")],
            }
        features = result.get("features", {})
        motor_spread = features.get("motor_spread_max", 0)
        
        diagnoses = result.get("diagnoses", [])
        motor_diag = next((d for d in diagnoses if d.get("failure_type") in ["motor_imbalance", "mechanical_failure"]), None)
        
        text = "Motor analysis: "
        if motor_diag:
            confidence = motor_diag.get("confidence", 0) * 100
            text += f"MOTOR ISSUE detected ({motor_diag['failure_type']}) with {confidence:.0f}% confidence. "
        else:
            text += "No motor imbalance detected. "
        
        text += f"Max output spread: {motor_spread:.1f}%. "
        if motor_spread > 15:
            text += "High spread indicates one motor producing less thrust than others."
        
        return {
            "text": text,
            "confidence": 0.85,
            "sources": ["RCOU message data", "Motor output analysis"],
            "follow_up": ["Identify weakest motor", "Check ESC calibration", "Inspect propellers"]
        }
    
    def _answer_compass_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer compass-related questions."""
        status, capability = self._capability_status(result, "compass_gps_navigation")
        missing = {str(item).upper() for item in capability.get("missing_messages", [])}
        if status in {"UNSUPPORTED", "UNKNOWN"} or "MAG" in missing:
            return {
                "text": "Compass health cannot be assessed because MAG telemetry is missing or unsupported in this log.",
                "confidence": 0.1,
                "sources": ["quality_report.capabilities.compass_gps_navigation"],
                "follow_up": [capability.get("recommendation", "Capture MAG telemetry on the next flight.")],
            }
        features = result.get("features", {})
        mag_range = features.get("mag_field_range", 0)
        
        diagnoses = result.get("diagnoses", [])
        compass_diag = next((d for d in diagnoses if d.get("failure_type") == "compass_interference"), None)
        
        text = "Compass analysis: "
        if compass_diag:
            confidence = compass_diag.get("confidence", 0) * 100
            text += f"COMPASS INTERFERENCE detected with {confidence:.0f}% confidence. "
            text += f"Magnetic field range: {mag_range:.1f} mGauss (abnormal). "
            text += "This causes yaw drift and can lead to toilet-bowling in Loiter mode."
        else:
            text += f"Compass readings appear normal. Field range: {mag_range:.1f} mGauss."
        
        return {
            "text": text,
            "confidence": 0.9,
            "sources": ["MAG message data", "Compass interference detector"],
            "follow_up": ["Move compass away from power leads", "Run compass-mot calibration"]
        }
    
    def _answer_gps_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer GPS-related questions."""
        status, capability = self._capability_status(result, "compass_gps_navigation")
        missing = {str(item).upper() for item in capability.get("missing_messages", [])}
        if status in {"UNSUPPORTED", "UNKNOWN"} or "GPS" in missing:
            return {
                "text": "GPS quality cannot be assessed because GPS telemetry is missing or unsupported in this log.",
                "confidence": 0.1,
                "sources": ["quality_report.capabilities.compass_gps_navigation"],
                "follow_up": [capability.get("recommendation", "Capture GPS telemetry on the next flight.")],
            }
        features = result.get("features", {})
        hdop_max = features.get("gps_hdop_max", 0)
        gps_fix_pct = features.get("gps_fix_pct", 100)
        
        text = "GPS status: "
        if hdop_max > 2.0:
            text += f"GPS quality POOR. Max HDOP: {hdop_max:.2f} (should be < 1.4). "
            text += "This degrades navigation accuracy and can trigger EKF failsafes."
        elif hdop_max > 1.4:
            text += f"GPS quality MARGINAL. Max HDOP: {hdop_max:.2f}. "
            text += "Acceptable but not ideal for precision flight."
        else:
            text += f"GPS quality GOOD. Max HDOP: {hdop_max:.2f}. "
        
        if gps_fix_pct < 100:
            text += f" GPS fix available {gps_fix_pct:.0f}% of flight time."
        
        return {
            "text": text,
            "confidence": 0.9,
            "sources": ["GPS message data"],
            "follow_up": ["Ensure clear sky view", "Check GPS antenna placement"]
        }
    
    def _answer_power_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer power/battery-related questions."""
        status, capability = self._capability_status(result, "power_battery_dynamics")
        if status in {"UNSUPPORTED", "UNKNOWN"}:
            return {
                "text": "Power health cannot be assessed because BAT/CURR/POWR telemetry is missing or unsupported in this log.",
                "confidence": 0.1,
                "sources": ["quality_report.capabilities.power_battery_dynamics"],
                "follow_up": [capability.get("recommendation", "Capture battery and current telemetry on the next flight.")],
            }
        features = result.get("features", {})
        bat_volt_min = features.get("bat_volt_min", 0)
        bat_sag = features.get("bat_sag_ratio", 0)
        
        diagnoses = result.get("diagnoses", [])
        power_diag = next((d for d in diagnoses if d.get("failure_type") in ["power_instability", "brownout"]), None)
        
        text = "Power system analysis: "
        if power_diag:
            confidence = power_diag.get("confidence", 0) * 100
            text += f"POWER ISSUE detected ({power_diag['failure_type']}) with {confidence:.0f}% confidence. "
        
        text += f"Min voltage: {bat_volt_min:.2f}V"
        if bat_sag > 0.15:
            text += f", Voltage sag: {bat_sag*100:.1f}% (excessive)"
        
        return {
            "text": text,
            "confidence": 0.85,
            "sources": ["BAT message data", "Power analysis"],
            "follow_up": ["Check battery cell health", "Verify power module connections"]
        }
    
    def _answer_root_cause_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer root cause questions."""
        explain_data = result.get("explain_data", {})
        decision = explain_data.get("decision", {})
        
        diagnoses = result.get("diagnoses", [])
        if not diagnoses:
            return {
                "text": "No diagnosis available for this log.",
                "confidence": 0.5
            }
        
        primary = diagnoses[0]
        text = f"ROOT CAUSE: {primary['failure_type'].upper().replace('_', ' ')} "
        text += f"({primary.get('confidence', 0)*100:.0f}% confidence)\n\n"
        
        if "evidence" in primary:
            text += f"Evidence: {'; '.join(primary['evidence'][:3])}\n"
        
        if "reason" in decision:
            text += f"\nCausal reasoning: {decision['reason']}\n"
        
        if primary.get("detection_method") == "rule+ml":
            text += "\nThis diagnosis was confirmed by both physics-based rules AND machine learning."
        
        return {
            "text": text,
            "confidence": primary.get("confidence", 0.8),
            "sources": ["Hybrid diagnosis engine", "CITA causal arbiter"],
            "follow_up": ["View full timeline", "See recommendations"]
        }
    
    def _answer_timeline_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer timeline-related questions."""
        timeline_events = result.get("timeline_events", [])
        
        if not timeline_events:
            return {
                "text": "No timeline events recorded for this flight.",
                "confidence": 0.5
            }
        
        # Sort by timestamp
        sorted_events = sorted(timeline_events, key=lambda e: e.get("timestamp", 0))
        
        text = "Event Timeline:\n"
        for event in sorted_events[:5]:  # Show top 5 events
            ts = event.get("timestamp", 0)
            severity = event.get("severity", "info").upper()
            event_type = event.get("event_type", "unknown")
            text += f"T+{ts:.1f}s [{severity}] {event_type}\n"
        
        if len(sorted_events) > 5:
            text += f"...and {len(sorted_events) - 5} more events"
        
        return {
            "text": text,
            "confidence": 0.9,
            "sources": ["CITA temporal arbitration"],
            "follow_up": ["What was the first anomaly?", "Show critical events only"]
        }
    
    def _answer_confidence_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer confidence-related questions."""
        diagnoses = result.get("diagnoses", [])
        
        if not diagnoses:
            return {
                "text": "No diagnosis available to assess confidence.",
                "confidence": 0.5
            }
        
        primary = diagnoses[0]
        conf = primary.get("confidence", 0) * 100
        method = primary.get("detection_method", "unknown")
        
        text = f"Diagnosis confidence: {conf:.0f}%\n\n"
        text += f"Detection method: {method}\n"
        
        if method == "rule+ml":
            text += "✓ High reliability - confirmed by both rule engine AND ML classifier"
        elif method == "rule":
            text += "✓ Rule-based detection - based on ArduPilot domain knowledge thresholds"
        elif method == "ml":
            text += "✓ ML-based detection - pattern recognized by trained XGBoost model"
        else:
            text += "○ Lower confidence - manual review recommended"
        
        return {
            "text": text,
            "confidence": 0.95,
            "sources": ["Hybrid engine confidence calibration"],
            "follow_up": ["How is confidence calculated?", "What does CITA do?"]
        }
    
    def _answer_recommendation_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer recommendation-related questions."""
        diagnoses = result.get("diagnoses", [])
        
        if not diagnoses:
            return {
                "text": "No diagnosis available for recommendations.",
                "confidence": 0.5
            }
        
        primary = diagnoses[0]
        text = "RECOMMENDATIONS:\n\n"
        
        if "recommendation" in primary:
            text += f"Primary: {primary['recommendation']}\n\n"
        
        # Add specific checks based on failure type
        failure_type = primary.get("failure_type", "")
        checks = {
            "vibration_high": "1. Inspect all propellers for damage\n2. Check motor mount tightness\n3. Verify frame integrity",
            "compass_interference": "1. Move compass away from power leads\n2. Run compass-mot calibration\n3. Consider external GPS/compass mast",
            "motor_imbalance": "1. Identify weakest motor (highest PWM output)\n2. Swap motor to test\n3. Check ESC calibration",
            "ekf_failure": "1. Check upstream sensors (IMU, GPS, compass)\n2. Review vibration levels\n3. Verify sensor calibration",
        }
        
        if failure_type in checks:
            text += f"\nSpecific checks:\n{checks[failure_type]}"
        
        return {
            "text": text,
            "confidence": 0.9,
            "sources": ["Failure type recommendations database"],
            "follow_up": ["How do I fix this?", "Preventive maintenance tips"]
        }
    
    def _answer_summary_question(self, question: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Answer summary questions."""
        metadata = result.get("metadata", {})
        diagnoses = result.get("diagnoses", [])
        
        text = "FLIGHT SUMMARY\n"
        text += "=" * 40 + "\n"
        text += f"File: {metadata.get('filename', 'unknown')}\n"
        text += f"Duration: {metadata.get('duration', 0):.1f}s\n"
        text += f"Vehicle: {metadata.get('vehicle', 'unknown')}\n\n"
        
        if diagnoses:
            primary = diagnoses[0]
            text += f"DIAGNOSIS: {primary['failure_type'].upper().replace('_', ' ')}\n"
            text += f"Confidence: {primary.get('confidence', 0)*100:.0f}%\n"
            
            if "evidence" in primary and primary["evidence"]:
                text += f"\nKey evidence: {primary['evidence'][0]}\n"
        else:
            text += "No issues detected - flight appears healthy.\n"
        
        return {
            "text": text,
            "confidence": 0.95,
            "sources": ["Analysis metadata", "Diagnosis results"],
            "follow_up": ["What caused this?", "Show timeline", "Give recommendations"]
        }
    
    def _generic_response(self, result: Dict[str, Any]) -> str:
        """Generate a generic helpful response when no pattern matches."""
        diagnoses = result.get("diagnoses", [])
        
        text = "I'm not sure I understand that question. "
        text += "Try asking about:\n\n"
        text += "• 'Is the vibration normal?'\n"
        text += "• 'What caused the crash?'\n"
        text += "• 'Show me the timeline'\n"
        text += "• 'Why did EKF fail?'\n"
        text += "• 'What should I check?'\n"
        
        if diagnoses:
            text += f"\nCurrent diagnosis: {diagnoses[0]['failure_type'].replace('_', ' ').upper()}\n"
            text += f"Confidence: {diagnoses[0].get('confidence', 0)*100:.0f}%"
        
        return text
