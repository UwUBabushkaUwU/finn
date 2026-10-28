"""FINN pipeline configuration.

Loads environment variables and pipeline/portfolio.yaml.
Exposes portfolio tickers, research tickers, alert defaults, and model ids.
"""

from pathlib import Path
import os
import yaml
from dotenv import load_dotenv

# Resolve paths
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
ENV_PATH = PROJECT_ROOT / ".env"
PORTFOLIO_YAML_PATH = PIPELINE_DIR / "portfolio.yaml"

# Load .env if present
if ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)
else:
    load_dotenv()

# Read portfolio.yaml
if not PORTFOLIO_YAML_PATH.exists():
    raise FileNotFoundError(f"portfolio.yaml not found at {PORTFOLIO_YAML_PATH}")

with open(PORTFOLIO_YAML_PATH, "r", encoding="utf-8") as f:
    _yaml_data = yaml.safe_load(f) or {}

# Companies
PORTFOLIO: list[dict] = _yaml_data.get("portfolio", [])
RESEARCH: list[dict] = _yaml_data.get("research", [])

PORTFOLIO_TICKERS: list[str] = [c["ticker"] for c in PORTFOLIO if "ticker" in c]
RESEARCH_TICKERS: list[str] = [c["ticker"] for c in RESEARCH if "ticker" in c]
ALL_TICKERS: list[str] = PORTFOLIO_TICKERS + RESEARCH_TICKERS

# Alert defaults
ALERT_DEFAULTS: dict = _yaml_data.get("alerts", {})

# Model routing
MODEL_IDS: dict = _yaml_data.get("models", {})

# Secrets & Environment variables
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY", "")
NEXT_PUBLIC_SUPABASE_URL: str = os.getenv("NEXT_PUBLIC_SUPABASE_URL", "")
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: str = os.getenv("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY", "")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
SEARCH_API_KEY: str = os.getenv("SEARCH_API_KEY", "")
