import pandas as pd
import numpy as np

def apply_rolling_window_filter(df: pd.DataFrame, window_size: int = 5) -> pd.DataFrame:
    """
    Applies a moving-average rolling window filter to smooth out high-frequency 
    vibration and noise anomalies from raw ArduPilot sensor streams (IMU/GPS).
    
    Parameters:
    -----------
    df : pd.DataFrame
        The raw telemetry data matrix parsed from the ArduPilot log.
    window_size : int, default 5
        The size of the moving window (number of data rows).
        
    Returns:
    --------
    pd.DataFrame
        A clean copy of the DataFrame with target sensor metrics smoothed out.
    """
    # Reject bad configurations
    if window_size <= 0:
        raise ValueError("window_size must be a positive integer")
        
    # Maintain consistent copy semantics for empty data or window_size of 1
    if df.empty or window_size == 1:
        return df.copy()

    df_smoothed = df.copy()

    # Automatically map target noisy ArduPilot sensor column signatures
    target_keywords = ['imu', 'gyr', 'acc', 'gps', 'vibe']
    
    # Identify numeric columns that match our noisy sensor keywords
    columns_to_filter = [
        col for col in df.select_dtypes(include=[np.number]).columns 
        if any(keyword in str(col).lower() for keyword in target_keywords)
    ]

    if not columns_to_filter:
        return df_smoothed

    # Apply vectorized centered rolling mean computation 
    # min_periods=1 prevents NaN generation at the beginning rows of the log
    df_smoothed[columns_to_filter] = (
        df[columns_to_filter]
        .rolling(window=window_size, min_periods=1, center=True)
        .mean()
    )

    return df_smoothed
