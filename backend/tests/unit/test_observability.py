from app.observability import add_correlation_id, correlation_id_var


def test_processor_adds_correlation_id_when_set():
    token = correlation_id_var.set("abc")
    try:
        assert add_correlation_id(None, "info", {"event": "x"})["correlation_id"] == "abc"
    finally:
        correlation_id_var.reset(token)


def test_processor_leaves_event_alone_when_unset():
    assert "correlation_id" not in add_correlation_id(None, "info", {"event": "x"})
