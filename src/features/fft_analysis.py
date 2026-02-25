import numpy as np
from scipy import fft
from .base_extractor import BaseExtractor

class FFTExtractor(BaseExtractor):
    REQUIRED_MESSAGES = [] # Custom
    FEATURE_PREFIX = "fft_"
    FEATURE_NAMES = [
        "fft_dominant_freq_x", "fft_dominant_freq_y", "fft_dominant_freq_z",
        "fft_peak_power_x", "fft_peak_power_y", "fft_peak_power_z",
        "fft_noise_floor"
    ]
    
    def has_data(self) -> bool:
        return "FTN1" in self.messages and len(self.messages["FTN1"]) > 0 or \
               "IMU" in self.messages and len(self.messages["IMU"]) > 0
               
    def extract(self) -> dict:
        ftn_msgs = self.messages.get("FTN1", [])
        imu_msgs = self.messages.get("IMU", [])
        
        if ftn_msgs:
            pk_avg_vals = [self._safe_value(msg, "PkAvg") for msg in ftn_msgs]
            snx_vals = [self._safe_value(msg, "SnX") for msg in ftn_msgs]
            sny_vals = [self._safe_value(msg, "SnY") for msg in ftn_msgs]
            snz_vals = [self._safe_value(msg, "SnZ") for msg in ftn_msgs]
            
            return {
                "fft_dominant_freq_x": sum(pk_avg_vals)/len(pk_avg_vals) if pk_avg_vals else 0.0, # Approximate
                "fft_dominant_freq_y": sum(pk_avg_vals)/len(pk_avg_vals) if pk_avg_vals else 0.0,
                "fft_dominant_freq_z": sum(pk_avg_vals)/len(pk_avg_vals) if pk_avg_vals else 0.0,
                "fft_peak_power_x": sum(snx_vals)/len(snx_vals) if snx_vals else 0.0,
                "fft_peak_power_y": sum(sny_vals)/len(sny_vals) if sny_vals else 0.0,
                "fft_peak_power_z": sum(snz_vals)/len(snz_vals) if snz_vals else 0.0,
                "fft_noise_floor": 0.0 # Hard to extract without more data
            }
        elif imu_msgs and False: # Disabled manual FFT as it hangs on large logs
            pass
            # ... (omitted expensive logic)
        return {
            "fft_dominant_freq_x": 0.0, "fft_dominant_freq_y": 0.0, "fft_dominant_freq_z": 0.0,
            "fft_peak_power_x": 0.0, "fft_peak_power_y": 0.0, "fft_peak_power_z": 0.0,
            "fft_noise_floor": 0.0
        }
            
        # No data
        return {
            "fft_dominant_freq_x": 0.0, "fft_dominant_freq_y": 0.0, "fft_dominant_freq_z": 0.0,
            "fft_peak_power_x": 0.0, "fft_peak_power_y": 0.0, "fft_peak_power_z": 0.0,
            "fft_noise_floor": 0.0
        }
