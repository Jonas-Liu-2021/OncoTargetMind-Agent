"""Entry point for Streamlit UI.

Usage:
    F:\AI\envs\llm\python.exe run_ui.py
"""
import os
import sys
import subprocess

if __name__ == "__main__":
    app_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app", "streamlit_app.py")
    subprocess.run([sys.executable, "-m", "streamlit", "run", app_path, "--server.port", "8501"])
