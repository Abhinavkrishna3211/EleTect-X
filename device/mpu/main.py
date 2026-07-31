"""BENCH-ONLY placeholder Python entry point for the eletect-x Arduino App.

This is NOT the production MPU entry point. It exists only so App Lab's
`app.yaml` parser accepts the app and `arduino-app-cli app restart` has
something to build/run - arduino-app-cli requires a `main.py` at the root of
`python/` by convention (not something `app.yaml` itself declares), and this
repo has never tracked one (confirmed via `git log -- device/mpu/main.py`
before this file was added). A file matching this name previously existed
on the board only, untracked, most likely left over from App Lab's original
"New App" scaffolding wizard - a `sync-to-board.sh` run legitimately deleted
it (`--delete` mirrors the repo exactly, and the repo had nothing here), which
is what broke the app tonight (docs/KNOWN_GAPS.md, "eletect-x python/main.py
missing" entry).

The real production entry point - wiring `bridge/`, `cognition/`,
`perception/`, and `services/` together into the actual sense -> fuse ->
decide -> actuate loop - is untracked, missing, and needs its own design
pass before field deployment. Nothing below should be read as a preview of
that design; this file deliberately does not import or call anything from
`bridge/rpc.py` (every function there is a signatures-only stub that raises
`NotImplementedError` - see that module's own header) or from `cognition/`,
`perception/`, `services/`. Wiring any of those in here would misrepresent
unfinished integration work as done.

Mirrors device/mpu/bench/ping/python/main.py's own pattern in every other
respect: import the Bridge SDK (so a real import-time failure of the App Lab
Python environment surfaces here rather than being masked), block forever.
Same UNVERIFIED caveat as that file: it is not confirmed whether App Lab's
own runtime keeps the process alive after registration alone or whether the
script itself must block - blocking is the safe assumption either way.

One registration, per the one-at-a-time discipline `DEVICE_DEVELOPMENT_WORKFLOW.md`
3 documents (a live, reproducible bug where an additional `Bridge.provide()`
broke previously-working ones on the same sketch): the receive side of
SEISMIC_DEBUG_STREAM_RAW's second, Bridge.notify()-based delivery path
(device/mcu/src/geophone.cpp - see config.h for the full rationale). This is
still schema-free and disposable, same as the rest of this file; it does not
touch bridge/rpc.py's stubs.
"""

import time

from arduino.app_utils import Bridge


def debug_stream_raw_seismic_sample(volts: float) -> None:
    """Bench-only: re-print one raw geophone volts sample on the MPU's stdout.

    Receive side of SEISMIC_DEBUG_STREAM_RAW's Bridge.notify() path
    (device/mcu/src/geophone.cpp) - a live alternative to that flag's
    existing Serial.println path, read via
    `docker logs -f eletect-x-main-1 | python scripts/live_seismic_plot.py -`.
    Prints in exactly the wire format scripts/live_seismic_plot.py's
    parse_raw_volts_line() already expects (bare float, 6 decimals, one per
    line) so that script needs no changes. Notify target, per
    device/mpu/bridge/rpc.py's own convention: no return value - the MCU
    never waits on one.

    Args:
        volts: Raw geophone reading in volts, as sent by geophone_cpp's
            Bridge.notify("debug_stream_raw_seismic_sample", volts) call.
    """
    print(f"{volts:.6f}")


Bridge.provide("debug_stream_raw_seismic_sample", debug_stream_raw_seismic_sample)

# UNVERIFIED: whether App Lab's own runtime keeps this process alive after
# registration, or whether the script itself must block. Blocking here is
# the safe assumption either way - it is a no-op if the runtime already
# keeps the process alive, and required if it doesn't.
while True:
    time.sleep(1)
