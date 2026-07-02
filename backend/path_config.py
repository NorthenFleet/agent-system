"""Shared filesystem paths for the running team-dashboard project."""

import os
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("TEAM_DASHBOARD_ROOT", BACKEND_ROOT.parent)).expanduser().resolve()
DATA_DIR = PROJECT_ROOT / "data"
BACKEND_DATA_DIR = BACKEND_ROOT / "data"


def project_path(*parts: str) -> str:
    return str(PROJECT_ROOT.joinpath(*parts))


def data_path(*parts: str) -> str:
    return str(DATA_DIR.joinpath(*parts))


def backend_data_path(*parts: str) -> str:
    return str(BACKEND_DATA_DIR.joinpath(*parts))
