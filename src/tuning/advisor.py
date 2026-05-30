"""Tuning advisor for PID analysis and tuning recommendations."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class TuningRecommendation:
    """A single tuning recommendation with confidence."""
    parameter: str
    current_value: Optional[float]
    suggested_value: Optional[float]
    reason: str
    confidence: float
    priority: str  # "high", "medium", "low"


class TuningAdvisor:
    """
    Analyzes flight log features and provides tuning recommendations.
    
    Covers:
    - PID step-response analysis (rise time, overshoot, settling)
    - FFT vibration source attribution (prop vs motor vs frame)
    - Basic filter suggestions
    - Thrust hover estimation
    """
    
    # Default thresholds for tuning analysis
    THRUST_HOVER_IDEAL = (0.45, 0.60)  # Ideal hover thrust range (45-60%)
    VIBE_FREQ_PROP_RANGE = (20, 60)  # Hz - typical propeller vibration frequencies
    VIBE_FREQ_MOTOR_RANGE = (60, 150)  # Hz - typical motor/ESC vibrations
    VIBE_FREQ_FRAME_RANGE = (150, 300)  # Hz - frame resonance
    
    def __init__(self):
        """Initialize the tuning advisor."""
        pass
    
    def analyze(self, features: Dict[str, Any], parsed_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Analyze flight data and generate tuning recommendations.
        
        Args:
            features: Extracted features from the feature pipeline
            parsed_data: Optional raw parsed log data for deeper analysis
            
        Returns:
            Dictionary containing tuning analysis and recommendations
        """
        recommendations = []
        
        # Analyze thrust hover
        thrust_rec = self._analyze_thrust_hover(features)
        if thrust_rec:
            recommendations.append(thrust_rec)
        
        # Analyze vibration spectrum (if FFT data available)
        vibe_recs = self._analyze_vibration_spectrum(features)
        recommendations.extend(vibe_recs)
        
        # Analyze PID response (if attitude data available)
        pid_recs = self._analyze_pid_response(features, parsed_data)
        recommendations.extend(pid_recs)
        
        # Analyze filter settings
        filter_recs = self._analyze_filter_settings(features)
        recommendations.extend(filter_recs)
        
        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: priority_order.get(r.priority, 3))
        
        return {
            "recommendations": [self._rec_to_dict(r) for r in recommendations],
            "summary": self._generate_summary(recommendations),
            "thrust_hover_estimate": features.get("thrust_hover_est", None),
            "vibration_analysis": self._summarize_vibration(features)
        }
    
    def _analyze_thrust_hover(self, features: Dict[str, Any]) -> Optional[TuningRecommendation]:
        """Analyze thrust hover percentage and provide recommendations."""
        thrust_hover = features.get("thrust_hover_est")
        
        if thrust_hover is None:
            # Try to estimate from motor outputs
            motor_avg = features.get("motor_out_avg", 0.5)
            if motor_avg > 0:
                thrust_hover = motor_avg
            else:
                return None
        
        if thrust_hover < self.THRUST_HOVER_IDEAL[0]:
            return TuningRecommendation(
                parameter="MOT_THST_HOVER",
                current_value=thrust_hover,
                suggested_value=(self.THRUST_HOVER_IDEAL[0] + self.THRUST_HOVER_IDEAL[1]) / 2,
                reason=f"Thrust hover ({thrust_hover:.1%}) is below ideal range ({self.THRUST_HOVER_IDEAL[0]:.0%}-{self.THRUST_HOVER_IDEAL[1]:.0%}). "
                       f"Aircraft may be under-propped or overweight. Consider lighter props or reducing weight.",
                confidence=0.8,
                priority="medium"
            )
        elif thrust_hover > self.THRUST_HOVER_IDEAL[1]:
            return TuningRecommendation(
                parameter="MOT_THST_HOVER",
                current_value=thrust_hover,
                suggested_value=(self.THRUST_HOVER_IDEAL[0] + self.THRUST_HOVER_IDEAL[1]) / 2,
                reason=f"Thrust hover ({thrust_hover:.1%}) is above ideal range. "
                       f"Aircraft is operating near max thrust - risky for aggressive maneuvers. "
                       f"Consider larger props, lower KV motors, or reducing weight.",
                confidence=0.85,
                priority="high"
            )
        
        return None
    
    def _analyze_vibration_spectrum(self, features: Dict[str, Any]) -> List[TuningRecommendation]:
        """Analyze vibration frequency spectrum to identify sources."""
        recommendations = []
        
        # Check if FFT data is available
        fft_peaks = features.get("fft_peaks", [])
        vibe_x_mean = features.get("vibe_x_mean", 0)
        vibe_y_mean = features.get("vibe_y_mean", 0)
        vibe_z_mean = features.get("vibe_z_mean", 0)
        
        if not fft_peaks and vibe_z_mean < 15:
            # No significant vibration, no recommendations needed
            return recommendations
        
        # Analyze dominant frequency if available
        if fft_peaks:
            dominant_freq = fft_peaks[0].get("frequency", 0) if fft_peaks else 0
            
            if dominant_freq > 0:
                if self.VIBE_FREQ_PROP_RANGE[0] <= dominant_freq <= self.VIBE_FREQ_PROP_RANGE[1]:
                    recommendations.append(TuningRecommendation(
                        parameter="INS_GYRO_FILTER",
                        current_value=None,
                        suggested_value=None,
                        reason=f"Dominant vibration at {dominant_freq:.1f} Hz suggests PROPELLER imbalance. "
                               f"This is in the typical propeller frequency range. "
                               f"Check propeller balance, inspect for damage, verify tight mounting.",
                        confidence=0.75,
                        priority="high"
                    ))
                elif self.VIBE_FREQ_MOTOR_RANGE[0] <= dominant_freq <= self.VIBE_FREQ_MOTOR_RANGE[1]:
                    recommendations.append(TuningRecommendation(
                        parameter="Motor/ESC",
                        current_value=None,
                        suggested_value=None,
                        reason=f"Dominant vibration at {dominant_freq:.1f} Hz suggests MOTOR/ESC issue. "
                               f"This is in the typical motor bearing/ESC PWM frequency range. "
                               f"Check motor bearings for play, verify ESC timing and PWM frequency.",
                        confidence=0.7,
                        priority="high"
                    ))
                elif self.VIBE_FREQ_FRAME_RANGE[0] <= dominant_freq <= self.VIBE_FREQ_FRAME_RANGE[1]:
                    recommendations.append(TuningRecommendation(
                        parameter="Frame/Structure",
                        current_value=None,
                        suggested_value=None,
                        reason=f"Dominant vibration at {dominant_freq:.1f} Hz suggests FRAME RESONANCE. "
                               f"This is structural vibration - check for loose standoffs, cracked arms, "
                               f"or insufficient damping between FC and frame.",
                        confidence=0.65,
                        priority="medium"
                    ))
        
        # High overall vibration without FFT - generic recommendation
        total_vibe = vibe_x_mean + vibe_y_mean + vibe_z_mean
        if total_vibe > 50 and not fft_peaks:
            recommendations.append(TuningRecommendation(
                parameter="Vibration Damping",
                current_value=None,
                suggested_value=None,
                reason=f"High overall vibration detected ({total_vibe:.1f} m/s² total). "
                       f"Without FFT data, cannot pinpoint exact source. "
                       f"Recommend: (1) Check all propellers, (2) Inspect motor mounts, "
                       f"(3) Verify FC mounting isolation, (4) Consider software low-pass filter adjustment.",
                confidence=0.6,
                priority="high"
            ))
        
        return recommendations
    
    def _analyze_pid_response(self, features: Dict[str, Any], parsed_data: Optional[Dict[str, Any]]) -> List[TuningRecommendation]:
        """Analyze PID step response for oscillation detection."""
        recommendations = []
        
        # Check for oscillation indicators
        attitude_osc = features.get("attitude_osc_detected", False)
        osc_frequency = features.get("oscillation_frequency", 0)
        osc_amplitude = features.get("oscillation_amplitude", 0)
        
        if attitude_osc:
            recommendations.append(TuningRecommendation(
                parameter="ATC_RAT_RLL_P, ATC_RAT_PIT_P",
                current_value=None,
                suggested_value="Reduce by 15-20%",
                reason=f"Oscillation detected at {osc_frequency:.1f} Hz with amplitude {osc_amplitude:.1f}°. "
                       f"This indicates PID gains are too aggressive. "
                       f"Reduce ATC_RAT_RLL_P and ATC_RAT_PIT_P by 15-20%, then test again.",
                confidence=0.8,
                priority="high"
            ))
        
        # Check for slow response (if we have rise time data)
        rise_time = features.get("step_rise_time", None)
        if rise_time and rise_time > 0.3:
            recommendations.append(TuningRecommendation(
                parameter="ATC_RAT_RLL_P, ATC_RAT_PIT_P",
                current_value=None,
                suggested_value="Increase by 10-15%",
                reason=f"Slow step response detected (rise time: {rise_time:.2f}s). "
                       f"Aircraft responds sluggishly to commands. "
                       f"Consider increasing rate P gains by 10-15% for crisper response.",
                confidence=0.7,
                priority="low"
            ))
        
        return recommendations
    
    def _analyze_filter_settings(self, features: Dict[str, Any]) -> List[TuningRecommendation]:
        """Analyze and suggest filter settings."""
        recommendations = []
        
        vibe_clip_total = features.get("vibe_clip_total", 0)
        vibe_z_mean = features.get("vibe_z_mean", 0)
        
        # If high vibration but no clipping, filters might be too aggressive
        if vibe_z_mean > 30 and vibe_clip_total == 0:
            recommendations.append(TuningRecommendation(
                parameter="INS_GYRO_FILTER",
                current_value=None,
                suggested_value="Consider reducing from default 20Hz",
                reason=f"High vibration ({vibe_z_mean:.1f} m/s²) without IMU clipping suggests "
                       f"current filters may be too aggressive, causing phase lag. "
                       f"Try reducing INS_GYRO_FILTER to 15Hz and monitor EKF performance.",
                confidence=0.6,
                priority="medium"
            ))
        
        # If clipping occurs, suggest notch filters
        if vibe_clip_total > 50:
            recommendations.append(TuningRecommendation(
                parameter="INS_HNTCH_ENABLE",
                current_value=None,
                suggested_value=1,
                reason=f"Significant IMU clipping detected ({vibe_clip_total:.0f} clips). "
                       f"Strongly recommend enabling harmonic notch filters (INS_HNTCH_ENABLE=1). "
                       f"Run 'motors set' in Motor Test to auto-tune notch frequencies.",
                confidence=0.85,
                priority="high"
            ))
        
        return recommendations
    
    def _rec_to_dict(self, rec: TuningRecommendation) -> Dict[str, Any]:
        """Convert TuningRecommendation to dictionary."""
        return {
            "parameter": rec.parameter,
            "current_value": rec.current_value,
            "suggested_value": rec.suggested_value,
            "reason": rec.reason,
            "confidence": rec.confidence,
            "priority": rec.priority
        }
    
    def _generate_summary(self, recommendations: List[TuningRecommendation]) -> str:
        """Generate human-readable summary of tuning analysis."""
        if not recommendations:
            return "✓ No critical tuning issues detected. Aircraft appears well-tuned."
        
        high_priority = sum(1 for r in recommendations if r.priority == "high")
        medium_priority = sum(1 for r in recommendations if r.priority == "medium")
        
        summary_parts = []
        if high_priority > 0:
            summary_parts.append(f"⚠️ {high_priority} high-priority tuning issue(s) found")
        if medium_priority > 0:
            summary_parts.append(f"⚡ {medium_priority} medium-priority issue(s)")
        
        if high_priority == 0 and medium_priority == 0:
            summary_parts.append("ℹ️ Minor optimization suggestions available")
        
        return ". ".join(summary_parts) + "."
    
    def _summarize_vibration(self, features: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize vibration analysis."""
        vibe_x = features.get("vibe_x_mean", 0)
        vibe_y = features.get("vibe_y_mean", 0)
        vibe_z = features.get("vibe_z_mean", 0)
        clip_total = features.get("vibe_clip_total", 0)
        
        total = vibe_x + vibe_y + vibe_z
        
        status = "nominal"
        if clip_total > 100:
            status = "critical"
        elif total > 50:
            status = "high"
        elif total > 30:
            status = "elevated"
        
        return {
            "vibe_x_mean": vibe_x,
            "vibe_y_mean": vibe_y,
            "vibe_z_mean": vibe_z,
            "total": total,
            "clipping_count": clip_total,
            "status": status,
            "source_attribution": self._attribute_vibration_source(features)
        }
    
    def _attribute_vibration_source(self, features: Dict[str, Any]) -> str:
        """Attribute vibration to likely source based on characteristics."""
        fft_peaks = features.get("fft_peaks", [])
        
        if fft_peaks:
            dominant_freq = fft_peaks[0].get("frequency", 0) if fft_peaks else 0
            if 20 <= dominant_freq <= 60:
                return "propeller"
            elif 60 <= dominant_freq <= 150:
                return "motor_esc"
            elif 150 <= dominant_freq <= 300:
                return "frame_resonance"
        
        # Fallback heuristic
        vibe_z = features.get("vibe_z_mean", 0)
        vibe_clip = features.get("vibe_clip_total", 0)
        
        if vibe_clip > 100:
            return "severe_mechanical"
        elif vibe_z > 40:
            return "likely_propeller"
        else:
            return "unknown"


def get_tuning_report(features: Dict[str, Any], parsed_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Convenience function to get a complete tuning report.
    
    Args:
        features: Extracted features
        parsed_data: Optional raw parsed data
        
    Returns:
        Complete tuning analysis report
    """
    advisor = TuningAdvisor()
    return advisor.analyze(features, parsed_data)
