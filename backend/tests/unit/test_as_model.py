from pydantic import BaseModel

from app.agents.nodes import as_model, repair_message


class Point(BaseModel):
    x: int


def test_as_model_accepts_model_dict_and_json():
    assert as_model(Point, Point(x=1)).x == 1
    assert as_model(Point, {"x": 2}).x == 2
    assert as_model(Point, '{"x": 3}').x == 3


def test_repair_message_lists_errors_and_asks_for_the_complete_object():
    message = repair_message(["variants.0.headline: too long"])
    assert "variants.0.headline: too long" in message
    assert "complete" in message.lower()
