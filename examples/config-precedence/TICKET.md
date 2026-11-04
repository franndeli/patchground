# Configuration overrides discard valid values

The deployment preview combines team defaults, environment settings and a final
operator override. An operator sets `replicas` to zero and disables a banner, but
the preview keeps the defaults. Two overrides at the same priority also choose
the earlier value instead of the final edit.

Repair `merge_layers(layers)` in `src/configuration.py`. Keep its public interface
and add a regression check under `tests/`.

## Input and output

Import `Layer` and `merge_layers` from `configuration`. A layer is a mapping with
`priority: int` and `values: Mapping[str, object]`. Values are already-parsed,
JSON-compatible data, including nested lists and objects. The function accepts
a sequence of layers and returns a new dictionary of settings. Inputs are
prevalidated. No file parsing, environment expansion or schema validation is needed.

For example, these layers:

```python
[
    {"priority": 1, "values": {"replicas": 3, "banner": True}},
    {"priority": 5, "values": {"replicas": 0}},
    {"priority": 5, "values": {"banner": False}},
]
```

produce `{"replicas": 0, "banner": False}`.

## Required behavior

- Choose the highest integer priority separately for each key. Priorities may
  be negative, and layers need not arrive in priority order.
- For equal priorities, the later layer in input order wins for keys it contains.
- A missing key does not override anything. Explicit null (`None`), `False`,
  zero, `""`, `[]` and `{}` are real overrides, not missing values.
- Merge top-level keys only. Replace a nested value as a whole, without combining
  its child keys or list elements.
- Empty input returns `{}`. Empty layers are allowed.
- Do not mutate the input sequence, the layer mappings or their nested values.
  The contract does not require deep-copy isolation after the function returns.

Keep the change within the merge logic and regression checks. No new dependencies
are needed. Use Patchground checks in Docker, not host Python or pytest.

This original Patchground challenge is AI-generated. Its beginner difficulty and
30-minute timebox are estimates, not human-calibrated measurements.
