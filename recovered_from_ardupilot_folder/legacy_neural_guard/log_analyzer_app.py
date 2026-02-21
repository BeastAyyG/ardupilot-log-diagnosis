import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import joblib
import os
import tempfile
from pymavlink import mavutil

# Model Configuration
MODEL_FILE = "anomaly_model.joblib"

st.set_page_config(
    page_title="Reaper Drone Diagnostics | AI Log Analyzer",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for "Production Feel"
st.markdown("""
<style>
    .stApp {
        background-color: #0e1117;
        color: #c9d1d9;
    }
    .metric-card {
        background-color: #161b22;
        padding: 20px;
        border-radius: 10px;
        border: 1px solid #30363d;
        text-align: center;
    }
    h1, h2, h3 {
        color: #58a6ff;
    }
    .stAlert {
        background-color: #1f2428;
        border: 1px solid #da3633;
        color: #ff7b72;
    }
</style>
""", unsafe_allow_html=True)

def parse_log(uploaded_file):
    """
    Simulates parsing the uploaded .BIN file.
    In a real app, we'd use pymavlink properly, but Streamlit's file uploader
    requires saving to disk first for mavutil or using a byte stream wrapper.
    """
    with tempfile.NamedTemporaryFile(delete=False, suffix=".BIN") as tmp_file:
        tmp_file.write(uploaded_file.getvalue())
        tmp_path = tmp_file.name
    
    # Use existing extraction logic (inline or imported)
    # Reusing logic from extract_ai_data.py for simplicity in this demo
    data = []
    try:
        mlog = mavutil.mavlink_connection(tmp_path)
        while True:
            m = mlog.recv_match(type=['BAT', 'VIBE', 'ATT', 'RCOU'])
            if m is None:
                break
            msg_type = m.get_type()
            row = {'TimeUS': m.TimeUS}
            
            if msg_type == 'BAT':
                row.update({'Type': 'BAT', 'Volt': m.Volt, 'Curr': m.Curr})
            elif msg_type == 'VIBE':
                row.update({'Type': 'VIBE', 'VibeX': m.VibeX, 'VibeY': m.VibeY, 'VibeZ': m.VibeZ})
            elif msg_type == 'ATT':
                row.update({'Type': 'ATT', 'Roll': m.Roll, 'Pitch': m.Pitch, 'Yaw': m.Yaw})
            elif msg_type == 'RCOU':
                row.update({'Type': 'RCOU', 'C1': m.C1, 'C2': m.C2, 'C3': m.C3, 'C4': m.C4})
            
            if len(row) > 1: # Only add if we got data
                data.append(row)
    except Exception as e:
        st.error(f"Error parsing log: {e}")
        return pd.DataFrame()
    finally:
        os.remove(tmp_path)
        
    return pd.DataFrame(data)

def load_ai_model():
    if os.path.exists(MODEL_FILE):
        return joblib.load(MODEL_FILE)
    return None

# --- UI Layout ---
st.title("🚁 Reaper AI Log Diagnosis")
st.markdown("### Production-Grade Anomaly Detection System")

uploaded_file = st.sidebar.file_uploader("Upload Flight Log (.BIN or .LOG)", type=["BIN", "LOG"])

if uploaded_file is not None:
    with st.spinner('Parsing Log & Running AI Models...'):
        df = parse_log(uploaded_file)
        
        if not df.empty:
            # Prepare data
            features = ['Volt', 'Curr', 'VibeX', 'VibeY', 'VibeZ', 'Roll', 'Pitch', 'Yaw', 'C1', 'C2', 'C3', 'C4']
            
            # Interpolate to align asynchronous data for ML (ffill is fast/robust enough for demo)
            df_aligned = df.set_index('TimeUS')
            # Split types into columns? No, let's keep it simple.
            # Actually, the dataframe structure from extract_ai_data is mixed types in one table.
            # We need to pivot to get features for ML.
            
            # Pivot strategy: Resample or forward fill
            # Since our extraction script output one row per message, we need to restructure
            # But wait, our previous training script just took the raw rows and ffilled everything.
            # Let's pivot properly this time for "Production Quality".
            
            pivot_df = df.pivot_table(index='TimeUS', columns='Type', values=['Volt', 'Curr', 'VibeX', 'VibeY', 'VibeZ', 'Roll', 'Pitch', 'Yaw', 'C1', 'C2', 'C3', 'C4'])
            # Flatten columns
            pivot_df.columns = [f"{c[1]}_{c[0]}" if c[1] else c[0] for c in pivot_df.columns]
            
            # Rename back to expected features if needed, or just re-map
            # The extract script produced specific columns based on IF msg_type
            # Simpler approach: Just filter by type and merge on TimeUS (approx match) or ffill
            
            # Fallback to simple structure for speed:
            # We need a dense matrix for the model.
            ml_df = df.copy()
            # For each unique timestamp, we might not have all columns.
            # Let's just forward fill the sparse matrix.
            ml_df = ml_df.groupby('TimeUS').first().ffill().dropna()
            
            # Ensure all feature columns exist
            for col in features:
                if col not in ml_df.columns:
                    ml_df[col] = 0.0 # Default if sensor missing
            
            X = ml_df[features]
            
            # Load Model
            model = load_ai_model()
            anomalies = []
            health_score = 100
            
            if model:
                preds = model.predict(X)
                ml_df['is_anomaly'] = preds
                anomalies = ml_df[ml_df['is_anomaly'] == -1]
                anomaly_count = len(anomalies)
                total_points = len(ml_df)
                
                # Calculate Health Score
                health_score = max(0, 100 - (anomaly_count / total_points * 500)) # Penalize 5 points per % anomaly
                
                # Metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"<div class='metric-card'><h2>Health Score</h2><h1 style='color:{'#238636' if health_score > 80 else '#da3633'}'>{health_score:.1f}%</h1></div>", unsafe_allow_html=True)
                with col2:
                    st.markdown(f"<div class='metric-card'><h2>Anomalies Detected</h2><h1>{anomaly_count}</h1></div>", unsafe_allow_html=True)
                with col3:
                    st.markdown(f"<div class='metric-card'><h2>Flight Duration</h2><h1>{len(df)/50/60:.1f} min</h1></div>", unsafe_allow_html=True) # Approx
                
                # --- Interactive Charts with Anomaly Highlights ---
                
                # 1. Vibration Analysis
                fig_vibe = go.Figure()
                fig_vibe.add_trace(go.Scatter(x=ml_df.index, y=ml_df['VibeX'], name='Vibe X', line=dict(color='#8b949e')))
                # Add Anomaly Markers
                if not anomalies.empty:
                    fig_vibe.add_trace(go.Scatter(x=anomalies.index, y=anomalies['VibeX'], mode='markers', name='Anomaly', marker=dict(color='red', size=4)))
                
                fig_vibe.update_layout(title="Vibration Analysis (with AI Anomaly Detection)", template="plotly_dark", height=400)
                st.plotly_chart(fig_vibe, use_container_width=True)

                # 2. Battery & Power
                fig_pwr = go.Figure()
                fig_pwr.add_trace(go.Scatter(x=ml_df.index, y=ml_df['Volt'], name='Voltage (V)', line=dict(color='#58a6ff')))
                if not anomalies.empty:
                         fig_pwr.add_trace(go.Scatter(x=anomalies.index, y=anomalies['Volt'], mode='markers', name='Anomaly', marker=dict(color='red', size=4)))
                fig_pwr.update_layout(title="Power Systems", template="plotly_dark", height=400)
                st.plotly_chart(fig_pwr, use_container_width=True)
                
            else:
                st.warning("AI Model not found. Please train the model first.")
        else:
            st.error("Log file is empty or formatted incorrectly.")
else:
    st.info("Please upload a .BIN log file to begin analysis.")
    
    # generate sample button
    if st.button("Generate Sample Training Data (Run SITL)"):
        st.write("Running simulation... please wait...")
        # Call the generation script
        os.system("python3 generate_training_data.py")
        st.success("Data generation complete! You can now find fresh logs in `logs/train/`.")
