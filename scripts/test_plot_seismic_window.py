"""Tests for plot_seismic_window.py's parsing logic only - no rendering.

matplotlib is imported lazily inside _plot_dump specifically so these tests
can run without ever touching it (plot_seismic_window.py's own docstring).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from plot_seismic_window import WindowDump, parse_window_dumps


def test_parses_single_dump():
    """A single header+CSV pair round-trips into one WindowDump."""
    log_text = "[window] t=1234 n=4 rate_hz=250 unit=volts\n0.1,0.2,0.3,0.4\n"
    dumps = parse_window_dumps(log_text)
    assert dumps == [
        WindowDump(t_ms=1234, n=4, rate_hz=250, samples=(0.1, 0.2, 0.3, 0.4))
    ]


def test_parses_multiple_dumps_in_order():
    """Two dumps in one log parse out in file order."""
    log_text = (
        "[window] t=100 n=2 rate_hz=250 unit=volts\n"
        "1.0,2.0\n"
        "[window] t=200 n=3 rate_hz=250 unit=volts\n"
        "3.0,4.0,5.0\n"
    )
    dumps = parse_window_dumps(log_text)
    assert [d.t_ms for d in dumps] == [100, 200]
    assert dumps[0].samples == (1.0, 2.0)
    assert dumps[1].samples == (3.0, 4.0, 5.0)


def test_ignores_unrelated_lines():
    """[trigger]/[seismic]/[bias-check] lines and blanks don't confuse parsing."""
    log_text = (
        "[seismic] t=50 sta=0.01 lta=0.01 ratio=1.0\n"
        "\n"
        "[bias-check] raw=100 volts=0.006250\n"
        "[trigger] t=100 sta=0.05 lta=0.01 ratio=5.0 idx=12\n"
        "[window] t=100 n=2 rate_hz=250 unit=volts\n"
        "1.5,-1.5\n"
        "[seismic] t=150 sta=0.01 lta=0.01 ratio=1.0\n"
    )
    dumps = parse_window_dumps(log_text)
    assert len(dumps) == 1
    assert dumps[0] == WindowDump(t_ms=100, n=2, rate_hz=250, samples=(1.5, -1.5))


def test_negative_and_fractional_volts_parse():
    """The AC geophone signal swings negative - the CSV must round-trip that."""
    log_text = "[window] t=1 n=3 rate_hz=250 unit=volts\n-0.062500,0.0,0.062500\n"
    dumps = parse_window_dumps(log_text)
    assert dumps[0].samples == (-0.0625, 0.0, 0.0625)


def test_no_dumps_returns_empty_list():
    """A log with no [window] lines at all parses to an empty list, not an error."""
    log_text = "[trigger] t=1 sta=1 lta=1 ratio=1 idx=0\nsome other console noise\n"
    assert parse_window_dumps(log_text) == []


def test_header_with_no_following_line_is_skipped():
    """A [window] header as the very last line of a truncated log is dropped, not raised."""
    log_text = "[window] t=1 n=2 rate_hz=250 unit=volts"
    assert parse_window_dumps(log_text) == []


def test_header_followed_by_unparseable_csv_is_skipped_but_others_survive():
    """One corrupted dump doesn't take the rest of the log down with it."""
    log_text = (
        "[window] t=1 n=2 rate_hz=250 unit=volts\n"
        "not,a,float\n"
        "[window] t=2 n=2 rate_hz=250 unit=volts\n"
        "1.0,2.0\n"
    )
    dumps = parse_window_dumps(log_text)
    assert len(dumps) == 1
    assert dumps[0].t_ms == 2


def test_malformed_header_line_is_not_matched():
    """A near-miss header (missing a field) is treated as an ordinary line, not a partial match."""
    log_text = "[window] t=1 n=2 unit=volts\n1.0,2.0\n"
    assert parse_window_dumps(log_text) == []
