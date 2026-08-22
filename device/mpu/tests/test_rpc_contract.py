"""Enforce that bridge/rpc.py stays hand-written against schema.md, not drift.

ENGINEERING_CONVENTIONS.md 6: "Both sides are hand-written against this
table, not against each other's code." This test is what makes that a
checked invariant instead of a hope: it parses device/mpu/bridge/schema.md's
two function tables directly and asserts every row has a matching stub in
bridge.rpc with the same argument names, in the same order - and that no
extra Bridge-shaped stub exists without a schema row backing it.
"""

import inspect
import re
from pathlib import Path

import pytest

from bridge import rpc

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "bridge" / "schema.md"

# Row layout is identical in both tables: | `name` | `args` | ... | ... |
ROW_RE = re.compile(r"^\|\s*`(\w+)`\s*\|\s*`([^`]*)`\s*\|")


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not nested inside (), [] or {}.

    Needed because arg cells mix plain names (`schema_version`) with
    annotated ones that themselves contain commas or parens, e.g.
    `class_label: enum{gunshot, chainsaw, ...}` and
    `gain_pct: float (0-100)`.
    """
    parts: list[str] = []
    depth = 0
    current = ""
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def _arg_names(args_cell: str) -> list[str]:
    """Extract just the argument names from a schema.md Args cell, in order."""
    names = []
    for token in _split_top_level(args_cell):
        name = token.split(":", 1)[0].strip()
        names.append(name)
    return names


def _parse_schema_functions() -> dict[str, list[str]]:
    """Return {function_name: [arg_name, ...]} for every row in both tables."""
    functions: dict[str, list[str]] = {}
    text = SCHEMA_PATH.read_text(encoding="utf-8")
    for line in text.splitlines():
        match = ROW_RE.match(line)
        if not match:
            continue
        name, args_cell = match.group(1), match.group(2)
        # Header/separator rows and same-side contracts (not Bridge
        # functions) don't belong in this table - filter to the known
        # Bridge function names so a stray backticked table row elsewhere
        # in the doc can't be mistaken for a schema row.
        if name not in KNOWN_BRIDGE_FUNCTIONS:
            continue
        functions[name] = _arg_names(args_cell)
    return functions


# The eight real Bridge functions schema.md defines. Anchoring the parser to
# this explicit set (rather than "any backticked-name table row") keeps a
# same-side contract table row (e.g. read_seismic_window) from ever being
# mistaken for a Bridge function.
KNOWN_BRIDGE_FUNCTIONS = {
    "report_footfall_event",
    "report_acoustic_event",
    "report_system_status",
    "drive_horn",
    "drive_led",
    "pulse_ir",
    "get_system_state",
    "send_lora_alert",
}

SCHEMA_FUNCTIONS = _parse_schema_functions()


def test_schema_parse_found_all_eight_functions():
    """Sanity-check the parser itself before trusting it to check anything else."""
    assert set(SCHEMA_FUNCTIONS) == KNOWN_BRIDGE_FUNCTIONS, (
        f"Expected to parse exactly {sorted(KNOWN_BRIDGE_FUNCTIONS)} out of "
        f"schema.md, got {sorted(SCHEMA_FUNCTIONS)}. Either schema.md's table "
        "layout changed or the parser regex needs updating."
    )


@pytest.mark.parametrize("name", sorted(KNOWN_BRIDGE_FUNCTIONS))
def test_stub_exists_for_schema_function(name):
    """Every schema.md row has a same-named stub in bridge.rpc."""
    assert hasattr(rpc, name), (
        f"schema.md defines `{name}` but bridge/rpc.py has no stub for it."
    )


@pytest.mark.parametrize("name", sorted(KNOWN_BRIDGE_FUNCTIONS))
def test_stub_arg_names_match_schema(name):
    """The stub's parameter names must match schema.md's Args cell, in order."""
    func = getattr(rpc, name)
    actual_args = list(inspect.signature(func).parameters.keys())
    expected_args = SCHEMA_FUNCTIONS[name]
    assert actual_args == expected_args, (
        f"`{name}` argument mismatch: bridge/rpc.py has {actual_args}, "
        f"schema.md specifies {expected_args}."
    )


def test_no_extra_bridge_shaped_stubs():
    """No public function in bridge.rpc claims to be a Bridge function without a schema row."""
    public_functions = {
        name
        for name, obj in vars(rpc).items()
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and obj.__module__ == rpc.__name__
    }
    extra = public_functions - KNOWN_BRIDGE_FUNCTIONS
    assert not extra, (
        f"bridge/rpc.py defines {sorted(extra)}, which schema.md does not - "
        "either add the row to schema.md or rename/remove the stub."
    )


# ---------------------------------------------------------------------------
# Return types - schema.md's Return column, MPU -> MCU table only (the
# MCU -> MPU table's handlers are notify targets and return None).
# ---------------------------------------------------------------------------

EXPECTED_RETURN_ANNOTATIONS = {
    "report_footfall_event": None,
    "report_acoustic_event": None,
    "report_system_status": None,
    "drive_horn": bool,
    "drive_led": bool,
    "pulse_ir": bool,
    "get_system_state": rpc.SystemState,
    "send_lora_alert": bool,
}


@pytest.mark.parametrize("name", sorted(KNOWN_BRIDGE_FUNCTIONS))
def test_stub_return_annotation_matches_schema(name):
    """The stub's return annotation matches schema.md's Return column."""
    func = getattr(rpc, name)
    actual_return = inspect.signature(func).return_annotation
    expected_return = EXPECTED_RETURN_ANNOTATIONS[name]
    assert actual_return == expected_return, (
        f"`{name}` return type mismatch: bridge/rpc.py annotates "
        f"{actual_return}, schema.md implies {expected_return}."
    )
