"""
Central configuration for AIMS — paths and the shared .env location.

Single source of truth for where pipeline artifacts live on disk, so every
module (incident-management, root-cause, SLA, the UI, the viewers) agrees on
the layout. Import these constants instead of hard-coding paths.

Layout (everything is relative to the repo root, the parent of the aims/ package):
    data/
    ├── checklists/   Agent 1 output  (SOP → steps / compliance checklist)
    ├── verdicts/     Agent 2 output  → Agent 3 input
    ├── incidents/    Agent 3 output  (generated)
    ├── diagnoses/    Root-Cause output (generated)
    └── tickets_db.json   UI state (generated, gitignored)
"""

from pathlib import Path

# aims/config.py → aims/ → repo root
ROOT = Path(__file__).resolve().parent.parent

# Shared credentials file (LLM + email), gitignored. Modules load it via
# load_dotenv(ENV_FILE) before constructing their clients.
ENV_FILE = ROOT / ".env"

DATA_DIR = ROOT / "data"
CHECKLISTS_DIR = DATA_DIR / "checklists"
VERDICTS_DIR = DATA_DIR / "verdicts"
INCIDENTS_DIR = DATA_DIR / "incidents"
DIAGNOSES_DIR = DATA_DIR / "diagnoses"

TICKETS_DB = DATA_DIR / "tickets_db.json"

# Every directory that should exist before anything reads or writes data.
ALL_DIRS = (CHECKLISTS_DIR, VERDICTS_DIR, INCIDENTS_DIR, DIAGNOSES_DIR)


def ensure_dirs() -> None:
    """Create the data directories if they don't exist yet (idempotent)."""
    for d in ALL_DIRS:
        d.mkdir(parents=True, exist_ok=True)
