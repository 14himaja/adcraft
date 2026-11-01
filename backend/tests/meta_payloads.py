"""Load the verified Meta v26.0 payloads saved in Milestone 0 (docs/pay_loads)."""

import json
from pathlib import Path

PAYLOAD_DIR = Path(__file__).resolve().parents[2] / "docs" / "pay_loads"
M0_ACCOUNT = "act_2279071366267627"
M0_PAGE = "1415879818267624"


def m0(name: str) -> dict:
    return json.loads((PAYLOAD_DIR / f"{name}.json").read_text(encoding="utf-8"))
