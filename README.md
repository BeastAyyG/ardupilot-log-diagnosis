# ArduPilot Log Diagnosis Tool

GSoC 2025 prototype for Project 5: 
AI-Assisted Log Diagnosis.

## What It Does

Parses ArduPilot .BIN flight logs and detects:
- Vibration issues
- Compass interference
- Power problems
- GPS quality issues
- Motor imbalance

## Run It

pip install pymavlink numpy scikit-learn
python3 diagnosis_engine.py your_flight.BIN

## Author

[Your Name] — GSoC 2025 applicant
