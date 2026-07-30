"""Ping bench - Python (MPU) side of the hello-world Bridge round trip.

Registers exactly one Bridge function, per the one-at-a-time discipline
`DEVICE_DEVELOPMENT_WORKFLOW.md` 3 documents (a live, reproducible bug where
an additional `Bridge.provide()` broke previously-working ones on the same
sketch). This app is disposable and deliberately separate from the real
EleTect-X app and from device/mpu/bridge/rpc.py's schema stubs - it proves
the MCU -> MPU `Bridge.call()` direction works on this board at all, nothing
schema-shaped.

UNVERIFIED against real App Lab docs (docs/KNOWN_GAPS.md): the exact
Python entrypoint idiom (is a blocking run loop required after
`Bridge.provide()`, or does App Lab's own runtime keep the process alive?)
is written from `DEVICE_DEVELOPMENT_WORKFLOW.md` 2/3's description, not
confirmed against a real generated app. If this doesn't behave as written,
diff against the stock Blink LED example (confirmed working on this board
at Rung 0, `DEVICE_DEVELOPMENT_WORKFLOW.md` 6) before assuming the bridge
itself is broken.
"""

import time

from arduino.app_utils import Bridge  # noqa: F401  (board-only, see module docstring)


def ping(token: str) -> str:
    """Answer a ping with the same token echoed back inside the reply.

    Args:
        token: Opaque value the MCU side sends, printed back so the sketch
            can confirm the exact request that produced this reply.

    Returns:
        "pong:<token>" - a value the MCU can print verbatim to prove a real
        round trip happened, not just that a callback fired.
    """
    print(f"[ping] token={token} -> pong:{token}")
    return f"pong:{token}"


Bridge.provide("ping", ping)

# UNVERIFIED: whether App Lab's own runtime keeps this process alive after
# registration, or whether the script itself must block. Blocking here is
# the safe assumption either way - it is a no-op if the runtime already
# keeps the process alive, and required if it doesn't.
while True:
    time.sleep(1)
