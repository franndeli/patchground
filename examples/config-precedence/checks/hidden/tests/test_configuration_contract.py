from copy import deepcopy
from itertools import permutations

import pytest

from configuration import merge_layers


@pytest.mark.parametrize("value", [None, False, 0, "", [], {}])
def test_explicit_values_are_not_missing(value):
    layers = [
        {"priority": -9, "values": {"setting": "default", "untouched": 8}},
        {"priority": 4, "values": {"setting": value}},
        {"priority": 30, "values": {"other": "present"}},
    ]
    result = merge_layers(layers)
    assert result == {"setting": value, "untouched": 8, "other": "present"}
    assert type(result["setting"]) is type(value)


def test_distinct_priorities_ignore_input_order():
    layers = [
        {"priority": -30, "values": {"mode": "base", "path": "default"}},
        {"priority": -2, "values": {"mode": "middle"}},
        {"priority": 13, "values": {"mode": "final", "path": None}},
    ]
    for ordering in permutations(layers):
        assert merge_layers(ordering) == {"mode": "final", "path": None}


def test_each_key_has_its_own_winner_and_ties_follow_input_order():
    assert merge_layers([
        {"priority": 3, "values": {"a": 1, "b": 2}},
        {"priority": 100, "values": {"c": 3}},
        {"priority": 3, "values": {"a": 0, "d": 4}},
        {"priority": -1, "values": {"b": 9, "e": 5}},
        {"priority": 3, "values": {"d": None}},
        {"priority": 3, "values": {}},
    ]) == {"a": 0, "b": 2, "c": 3, "d": None, "e": 5}


def test_nested_objects_and_lists_replace_without_editing_sources():
    layers = [
        {"priority": 8, "values": {"obj": {"keep": [1]}, "items": [7, 9]}},
        {"priority": 8, "values": {"obj": {"new": {"enabled": False}}, "items": []}},
        {"priority": -4, "values": {"obj": {"old": 6}, "items": [3]}},
    ]
    before = deepcopy(layers)
    assert merge_layers(layers) == {"obj": {"new": {"enabled": False}}, "items": []}
    assert layers == before
    assert merge_layers(layers) == {"obj": {"new": {"enabled": False}}, "items": []}


def test_single_layer_preserves_all_json_value_kinds():
    values = {"n": None, "b": False, "i": 0, "s": "", "a": [], "o": {}, "f": 1.25}
    assert merge_layers(({"priority": 0, "values": values},)) == values
