from app.services.versions import content_hash, diff_versions


def test_hash_ignores_key_order():
    assert content_hash({"a": 1, "b": {"c": 2, "d": 3}}) == content_hash({"b": {"d": 3, "c": 2}, "a": 1})


def test_hash_changes_with_content():
    assert content_hash({"a": 1}) != content_hash({"a": 2})


def test_diff_lists_changed_paths():
    before = {"assets": {"variants": [{"headline": "Old", "description": "Same"}]}}
    after = {"assets": {"variants": [{"headline": "New", "description": "Same"}]}}
    assert diff_versions(before, after) == [
        {"path": "assets.variants.0.headline", "before": "Old", "after": "New"}
    ]


def test_diff_reports_added_list_items():
    before = {"variants": [{"h": "A"}]}
    after = {"variants": [{"h": "A"}, {"h": "B"}]}
    assert diff_versions(before, after) == [{"path": "variants.1", "before": None, "after": {"h": "B"}}]


def test_diff_of_equal_documents_is_empty():
    assert diff_versions({"a": [1, {"b": 2}]}, {"a": [1, {"b": 2}]}) == []
