from kycli.utils import coerce_value, try_parse_json


def test_coerce_value_startswith_json():
    assert coerce_value("123", json_mode="startswith") == 123
    assert coerce_value("true", json_mode="startswith") is True
    assert coerce_value("false", json_mode="startswith") is False
    assert coerce_value('{"a": 1}', json_mode="startswith") == {"a": 1}
    assert coerce_value("[1, 2]", json_mode="startswith") == [1, 2]
    assert coerce_value('"x"', json_mode="startswith") == '"x"'


def test_coerce_value_always_json():
    assert coerce_value('"x"', json_mode="always") == "x"
    assert coerce_value("123", json_mode="always") == 123
    assert coerce_value("true", json_mode="always") is True
    assert coerce_value("notjson", json_mode="always") == "notjson"


def test_try_parse_json():
    assert try_parse_json('{"a": 1}') == {"a": 1}
    assert try_parse_json("notjson") == "notjson"
    assert try_parse_json(10) == 10
