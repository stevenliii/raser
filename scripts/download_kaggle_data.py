import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
os.environ["KAGGLEHUB_CACHE"] = str(DATA_DIR)

try:
    import kagglehub
except ModuleNotFoundError:
    sys.exit("kagglehub is not installed. Run: pip install -r requirements.txt")

path = kagglehub.competition_download("gemma-4-developer-agent")
print("Path to competition files:", path)