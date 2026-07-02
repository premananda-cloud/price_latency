"""
src/config.py

Central config: environment variables and shared project paths.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Project root = parent of src/, regardless of what directory this is run from
BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

load_dotenv(ENV_FILE)

USDA_NASS_APIKEY = os.getenv("USDA_NASS_APIKEY")
if not USDA_NASS_APIKEY:
    raise RuntimeError(f"USDA_NASS_APIKEY not found — check {ENV_FILE}")

RAW_DATA_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DATA_DIR = BASE_DIR / "data" / "processed"
FIGURES_DIR = BASE_DIR / "figures"
