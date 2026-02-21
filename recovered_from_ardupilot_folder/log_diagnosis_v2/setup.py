from setuptools import setup, find_packages

setup(
    name="ardupilot-log-diagnosis",
    version="0.1.0",
    description="ArduPilot AI Log Diagnosis tool prototype",
    author="ArduPilot Team",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={"diagnosis": ["config/*.yaml"]},
    include_package_data=True,
    install_requires=[
        "pymavlink>=2.4.40",
        "numpy>=1.21.0",
        "scikit-learn>=1.0.0",
        "xgboost>=1.6.0",
        "pyyaml>=6.0",
    ],
    python_requires=">=3.8",
)
