from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"


def _sources():
    return {p: p.read_text(encoding="utf-8") for p in APP.rglob("*.py")}


def test_only_audit_module_touches_audit_log():
    allowed = {APP / "audit.py", APP / "db.py"}
    offenders = [str(p) for p, src in _sources().items() if p not in allowed and "audit_log" in src]
    assert offenders == []


def test_no_direct_datetime_now_outside_clock():
    offenders = [str(p) for p, src in _sources().items() if p.name != "clock.py" and "datetime.now(" in src]
    assert offenders == []


FORBIDDEN_IN_DOMAIN = (
    "pymongo",
    "httpx",
    "facebook_business",
    "google.adk",
    "litellm",
    "app.services",
    "app.agents",
    "app.meta",
    "app.api",
)


def test_domain_has_no_io_or_outer_layer_imports():
    offenders = [
        f"{p.name}: {bad}"
        for p, src in _sources().items()
        if "domain" in p.parts
        for bad in FORBIDDEN_IN_DOMAIN
        if f"import {bad}" in src or f"from {bad}" in src
    ]
    assert offenders == []


def test_only_the_sdk_gateway_imports_facebook_business():
    offenders = [
        str(p) for p, src in _sources().items() if p.name != "sdk_gateway.py" and "facebook_business" in src
    ]
    assert offenders == []


def test_gateways_are_constructed_only_in_the_container():
    offenders = [
        str(p)
        for p, src in _sources().items()
        if p.name != "container.py" and ("MetaSdkGateway(" in src or "FakeAdsGateway(" in src)
    ]
    assert offenders == []
