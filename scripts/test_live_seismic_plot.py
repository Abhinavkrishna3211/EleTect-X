"""Tests for live_seismic_plot.py's parsing logic only - no animation, no I/O.

matplotlib and pyserial are only imported lazily, inside _run_live_plot and
_iter_serial_lines respectively (live_seismic_plot.py's own docstring), so
these tests never touch either.
"""

import io
import sys
from contextlib import redirect_stderr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from live_seismic_plot import RatioSample, parse_ratio_line, parse_raw_volts_line


def test_parses_valid_raw_volts_line():
    """A bare float line parses to its value."""
    assert parse_raw_volts_line("0.001250\n") == 0.001250


def test_parses_negative_raw_volts_line():
    """The AC geophone signal swings negative - a negative bare float must parse."""
    assert parse_raw_volts_line("-0.062500\n") == -0.0625


def test_raw_volts_line_ignores_surrounding_whitespace():
    """Serial line endings/whitespace don't block parsing."""
    assert parse_raw_volts_line("  0.000625  \r\n") == 0.000625


def test_non_numeric_line_is_not_a_raw_volts_line():
    """An unrelated console line (e.g. a [seismic] line) is silently not a raw volts line."""
    assert parse_raw_volts_line("[seismic] t=100 sta=0.01 lta=0.01 ratio=1.00\n") is None


def test_empty_raw_volts_line_is_none():
    """An empty line parses to nothing, not an error."""
    assert parse_raw_volts_line("\n") is None
    assert parse_raw_volts_line("") is None


def test_non_finite_raw_volts_line_warns_and_returns_none():
    """A line that parses as a float but is not finite is dropped with a stderr warning."""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = parse_raw_volts_line("inf\n")
    assert result is None
    assert "not finite" in stderr.getvalue()


def test_parses_valid_ratio_line():
    """A well-formed [seismic] line round-trips into a RatioSample."""
    line = "[seismic] t=1234 sta=0.05 lta=0.01 ratio=5.00\n"
    assert parse_ratio_line(line) == RatioSample(t_ms=1234, sta=0.05, lta=0.01, ratio=5.00)


def test_ratio_line_with_negative_values_parses():
    """sta/lta/ratio are magnitudes in practice but the parser tolerates a signed value."""
    line = "[seismic] t=1 sta=-0.01 lta=0.02 ratio=-0.50\n"
    parsed = parse_ratio_line(line)
    assert parsed is not None
    assert parsed.sta == -0.01
    assert parsed.ratio == -0.50


def test_unrelated_line_is_not_a_ratio_line():
    """A raw volts line (or anything not tagged [seismic]) is silently not a ratio line."""
    assert parse_ratio_line("-0.001250\n") is None


def test_empty_ratio_line_is_none():
    """An empty line parses to nothing, not an error."""
    assert parse_ratio_line("\n") is None
    assert parse_ratio_line("") is None


def test_malformed_ratio_line_warns_and_returns_none():
    """A [seismic]-tagged line missing a field is dropped with a stderr warning, not raised."""
    stderr = io.StringIO()
    with redirect_stderr(stderr):
        result = parse_ratio_line("[seismic] t=100 sta=0.01 lta=0.01\n")
    assert result is None
    assert "did not match expected format" in stderr.getvalue()
