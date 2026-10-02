"""Verify wire_compat.install() forces non-fixint encoding for small ints.

msgpack is a transitive dependency of the on-device `arduino.app_utils`
package, not something this repo installs for laptop testing
(ENGINEERING_CONVENTIONS.md 1/4) - so every test here skips outright if
msgpack is not importable in the current environment, rather than adding it
as a dependency this package does not otherwise need.
"""

import pytest

msgpack = pytest.importorskip("msgpack")

from bridge import wire_compat  # noqa: E402 - importorskip must run first


@pytest.fixture(autouse=True)
def _reset_packer():
    """Restore msgpack.Packer and the install flag around each test.

    install() is meant to be called exactly once per process on the real
    board; tests need to exercise both the pre- and post-patch state, so
    each test gets a clean slate.
    """
    original_packer = msgpack.Packer
    yield
    msgpack.Packer = original_packer
    if hasattr(msgpack, "_eletect_nonfixint_patch_installed"):
        delattr(msgpack, "_eletect_nonfixint_patch_installed")


def test_install_returns_true_and_is_idempotent():
    """install() reports success and a second call is a harmless no-op."""
    assert wire_compat.install() is True
    patched_packer = msgpack.Packer
    assert wire_compat.install() is True
    assert msgpack.Packer is patched_packer


def test_small_nonnegative_int_no_longer_encodes_as_fixint():
    """Values 0-127 get the explicit uint8 (0xCC) prefix, not fixint."""
    wire_compat.install()
    for value in (0, 1, 2, 6, 100, 127):
        encoded = msgpack.packb(value)
        assert encoded[0] == 0xCC, f"value {value} still fixint-encoded: {encoded!r}"
        assert encoded == bytes([0xCC, value])


def test_values_at_or_above_128_are_unaffected():
    """Values already outside the fixint range keep their normal encoding."""
    wire_compat.install()
    unpatched = msgpack.packb(200, use_bin_type=True)
    # Rebuild what the unpatched C/fallback packer would emit for 200
    # (uint8 explicit form is already how any packer encodes it).
    assert unpatched == bytes([0xCC, 200])


def test_negative_ints_and_floats_are_unaffected():
    """Negative fixint and float encodings pass through untouched."""
    wire_compat.install()
    assert msgpack.packb(-5) == bytes([0xFB])  # negative fixint for -5
    assert msgpack.packb(1000) != b""  # sanity: still produces output


def test_nested_small_ints_inside_a_call_tuple_are_patched():
    """A realistic drive_led-shaped request tuple gets every small int patched.

    Mirrors the actual wire shape ClientServer.call() builds:
    [0, msgid, method_name, params] - the bug showed up on `channel` and
    `pattern_id` inside exactly this kind of nested tuple/list, not just on
    bare top-level values.
    """
    wire_compat.install()
    request = [0, 1, "drive_led", (128, 2, 0, 50.0, 1000)]
    encoded = msgpack.packb(request)
    unpacked = msgpack.unpackb(encoded)
    assert unpacked == [0, 1, "drive_led", [128, 2, 0, 50.0, 1000]]
    # channel=2 and pattern_id=0 must appear as explicit uint8 (0xCC 0x02 /
    # 0xCC 0x00), never as bare fixint bytes (0x02 / 0x00), inside the
    # packed params.
    assert bytes([0xCC, 2]) in encoded
    assert bytes([0xCC, 0]) in encoded


def test_without_install_small_ints_still_fixint_encode():
    """Sanity check on the baseline: proves the test actually detects the bug.

    Without calling install(), 0-127 must still round-trip through the
    default fixint format - otherwise the two tests above would pass for
    the wrong reason.
    """
    encoded = msgpack.packb(2)
    assert encoded == bytes([0x02])
