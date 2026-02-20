from .base_extractor import BaseExtractor

class IMUExtractor(BaseExtractor):
    REQUIRED_MESSAGES = ["IMU"]
    FEATURE_PREFIX = "imu_"
    FEATURE_NAMES = [
        "imu_acc_x_std", "imu_acc_y_std", "imu_acc_z_std",
        "imu_gyr_x_std", "imu_gyr_y_std", "imu_gyr_z_std"
    ]
    
    def extract(self) -> dict:
        imu_msgs = self.messages.get("IMU", [])
        
        acc_x_vals = [self._safe_value(msg, "AccX") for msg in imu_msgs]
        acc_y_vals = [self._safe_value(msg, "AccY") for msg in imu_msgs]
        acc_z_vals = [self._safe_value(msg, "AccZ") for msg in imu_msgs]
        
        gyr_x_vals = [self._safe_value(msg, "GyrX") for msg in imu_msgs]
        gyr_y_vals = [self._safe_value(msg, "GyrY") for msg in imu_msgs]
        gyr_z_vals = [self._safe_value(msg, "GyrZ") for msg in imu_msgs]
        
        acc_x_stats = self._safe_stats(acc_x_vals)
        acc_y_stats = self._safe_stats(acc_y_vals)
        acc_z_stats = self._safe_stats(acc_z_vals)
        
        gyr_x_stats = self._safe_stats(gyr_x_vals)
        gyr_y_stats = self._safe_stats(gyr_y_vals)
        gyr_z_stats = self._safe_stats(gyr_z_vals)
        
        return {
            "imu_acc_x_std": acc_x_stats["std"],
            "imu_acc_y_std": acc_y_stats["std"],
            "imu_acc_z_std": acc_z_stats["std"],
            "imu_gyr_x_std": gyr_x_stats["std"],
            "imu_gyr_y_std": gyr_y_stats["std"],
            "imu_gyr_z_std": gyr_z_stats["std"]
        }
