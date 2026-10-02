"""Workaround for a confirmed MsgPack encode/decode bug in the Bridge wire path.

Empirically confirmed on real hardware (2026-09-10 live session): any
unsigned-integer Bridge RPC parameter (`uint8_t` or `uint16_t` on the MCU
side) fails deserialization with MALFORMED_CALL_ERR ("Wrong type parameter
in position: N") whenever its value is msgpack-encoded as *positive fixint*
(format byte 0x00-0x7F, i.e. values 0-127 encoded in 1 byte). The same value
encoded in the explicit uint8 (0xCC) or wider format always succeeds. This
was isolated by holding every other field fixed and only varying whether one
field's value fell in the fixint range - e.g. `drive_led(..., channel=2,
pattern_id=0, ...)` fails on `channel`; `drive_led(..., channel=200,
pattern_id=0, ...)` fails on `pattern_id` instead, with `channel` now
accepted. The failure tracks encoded value magnitude, not parameter
position or width.

The bug's exact line was not pinpointed inside the vendored MCU-side
MsgPack_0.4.2 / Arduino_RPClite_0.3.0 libraries despite reading every layer
of the decode path (type-byte classification, per-type size table, the
`unpackable()` type-check, and value extraction) - all of which read as
correct standard MessagePack handling. Rather than risk another MCU reflash
chasing it live in the field with no one able to physically reach the board
until morning, this patches the MPU-side encoder instead: `drive_led`'s
`channel` (0-2) and `pattern_id` (0-6), and `drive_horn`'s `track_id` (1-5),
are exactly the small, legitimately-meaningful integers that land in the
fixint range on real calls, so bumping them (bridge/schema.md's earlier
SCHEMA_VERSION 4->128 fix, which only worked because schema_version itself
happened to be the sole small field in play) is not an option here.

`arduino.app_utils.bridge.ClientServer.notify()`/`.call()` (vendored into
the app container image, not part of this repo) encode every outgoing
request with the module-level `msgpack.packb()`, which builds its packer as
`Packer(**kwargs)` using the name `Packer` resolved from `msgpack`'s own
module namespace at call time - so replacing `msgpack.Packer` here is
sufficient to change what every `packb()` call in the process produces,
with no edit to the vendored file (which would not survive a container
rebuild anyway).

This module must stay importable with no board attached, same discipline as
bridge/rpc.py: `msgpack` is a transitive dependency of `arduino.app_utils`,
present in the on-device app container but not on a dev laptop
(ENGINEERING_CONVENTIONS.md 1/4). Nothing here imports it at module scope -
only `install()`, which is only ever called from main.py, on the board.
"""

_PATCH_FLAG = "_eletect_nonfixint_patch_installed"

# Positive fixint covers 0-127 inclusive (MessagePack spec, format byte
# 0x00-0x7F). Anything in this range is the one that trips the bug.
_FIXINT_MAX_EXCLUSIVE = 0x80


def install() -> bool:
    """Patch msgpack's packer so outgoing Bridge calls never emit fixint ints.

    Idempotent - safe to call more than once or from more than one module;
    the second call is a no-op. Forces any non-negative int below 128 to
    the explicit uint8 (0xCC) wire format instead of positive fixint.
    Negative ints, floats, and ints already >= 128 are untouched since they
    were never encoded as fixint to begin with.

    Returns:
        True if the patch is installed (either just now or already, by an
        earlier call). False if `msgpack` could not be imported - this
        should never happen inside the app container, but must not raise:
        a missing patch just leaves the pre-existing MCU decode bug in
        place for small-int params, the same behavior as never calling
        this at all, rather than crashing the reflex loop over a
        workaround for a bug that is not this function's to fix.
    """
    try:
        import msgpack
        import msgpack.fallback as fallback
    except ImportError:
        return False

    if getattr(msgpack, _PATCH_FLAG, False):
        return True

    import struct

    class _NonFixintPacker(fallback.Packer):
        """Pure-Python msgpack Packer that never emits positive fixint."""

        def _pack(
            self,
            obj,
            nest_limit=fallback.DEFAULT_RECURSE_LIMIT,
            check=isinstance,
            check_type_strict=fallback._check_type_strict,
        ):
            if check(obj, int) and not check(obj, bool) and 0 <= obj < _FIXINT_MAX_EXCLUSIVE:
                return self._buffer.write(struct.pack("BB", 0xCC, obj))
            return super()._pack(obj, nest_limit, check, check_type_strict)

    # msgpack.packb() (what ClientServer.notify()/.call() actually call)
    # builds its packer via the bare name `Packer`, resolved as a global in
    # msgpack/__init__.py's own namespace at call time - reassigning the
    # module attribute here is what makes packb() pick this up, with no
    # need to also override packb() itself.
    msgpack.Packer = _NonFixintPacker
    setattr(msgpack, _PATCH_FLAG, True)
    return True
