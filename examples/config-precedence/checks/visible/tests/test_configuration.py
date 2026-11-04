from copy import deepcopy

from configuration import merge_layers


def test_high_priority_wins_without_losing_unrelated_keys():
    layers = [
        {"priority": 20, "values": {"region": "west"}},
        {"priority": 1, "values": {"region": "east", "replicas": 3}},
    ]
    assert merge_layers(layers) == {"region": "west", "replicas": 3}


def test_later_layer_wins_a_priority_tie():
    assert merge_layers([
        {"priority": 5, "values": {"color": "blue", "region": "west"}},
        {"priority": 5, "values": {"color": "green"}},
    ]) == {"color": "green", "region": "west"}


def test_disabled_and_zero_values_override_defaults():
    assert merge_layers([
        {"priority": 0, "values": {"banner": True, "replicas": 3}},
        {"priority": 10, "values": {"banner": False, "replicas": 0}},
    ]) == {"banner": False, "replicas": 0}


def test_empty_input_and_empty_layers():
    assert merge_layers([]) == {}
    assert merge_layers([{"priority": 2, "values": {}}]) == {}


def test_nested_settings_replace_the_entire_value():
    assert merge_layers([
        {"priority": 1, "values": {"http": {"host": "local", "port": 80}}},
        {"priority": 2, "values": {"http": {"port": 443}}},
    ]) == {"http": {"port": 443}}


def test_inputs_remain_unchanged():
    layers = [
        {"priority": 10, "values": {"routes": ["api"], "http": {"port": 443}}},
        {"priority": -2, "values": {"routes": ["home"], "label": "preview"}},
    ]
    before = deepcopy(layers)
    merge_layers(layers)
    assert layers == before
