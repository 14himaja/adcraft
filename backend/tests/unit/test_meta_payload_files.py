import json
import re

import pytest

from tests.meta_payloads import PAYLOAD_DIR

FILES = sorted(PAYLOAD_DIR.glob("*.json"))
TOKEN_PATTERN = re.compile(r"EAA[A-Za-z0-9]{30,}")


def test_payload_directory_is_found():
    assert FILES, f"no payloads found in {PAYLOAD_DIR}"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_m0_payload_is_valid_json(path):
    json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_no_payload_contains_an_access_token(path):
    text = path.read_text(encoding="utf-8")
    assert not TOKEN_PATTERN.search(text), f"Potential access token found in {path.name}"
