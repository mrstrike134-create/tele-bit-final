import os
import runpy
import sys

APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "azure_quiz_platform")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)
os.chdir(APP_DIR)

if __name__ == "__main__":
    runpy.run_path(os.path.join(APP_DIR, "bot_runner.py"), run_name="__main__")
