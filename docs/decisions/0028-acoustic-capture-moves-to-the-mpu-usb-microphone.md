# ADR 0028: Acoustic capture moves to the MPU as a USB microphone — ADR 0009's on-MCU path is not buildable on this board

- **Status:** accepted
- **Date:** 2026-09-29

## Context

ADR 0009 placed acoustic capture on the MCU: an analog microphone sampled through a second ADC channel
under LPBAM, classified continuously in STOP mode, so a gunshot's 2–7 ms primary pulse is never raced by
a wake gate. ADR 0006 before it had established that the SAI peripheral was reachable at register level
even though the devicetree path was blocked. Both assumed the firmware could configure the peripherals it
needed.

On the UNO Q, it cannot. Three findings, in the order they bite:

1. **The Arduino core for this board ships a *prebuilt* Zephyr loader (LLEXT).** A sketch is loaded as an
   extension into a kernel image that was linked elsewhere. The devicetree is fixed at *loader* build
   time, not at sketch build time, so a sketch cannot add a SAI node at all. This is not the TrustZone
   restriction ADR 0006 worked around — it is earlier and more total, and register-level access does not
   route around it because the peripheral is never brought up or clocked.
2. **SAI sits outside the SmartRun low-power domain.** Even granting a way to configure it, it could not
   have delivered always-on listening at STOP-mode power, which was the entire reason ADR 0009 preferred a
   continuous design over a wake gate. The peripheral choice and the power argument fail together.
3. **The MAX9814 analog front end ADR 0009 depends on was dropped during procurement**
   (`hardware/bom/procurement-status.md`). The analog → ADC4 → LPBAM path has no hardware on the bench.

Against that, the MPU side has a working path today. The board runs Linux with ALSA; a USB audio class
device enumerates without drivers, without `sudo` and without `pip` — which matters, because the board's
Python 3.13.5 has no `pip` and no `ensurepip`, so nothing installable was ever an option. A BOYA BY-M1
lavalier plus a USB adapter, both already on hand, plug into the existing hub. The acoustic model is
already trained, already routed (`handle_acoustic_event`, ADR 0007 §5) and already reconciled to the wire
enum (ADR 0027). What was missing was capture, and the MPU has it.

## Decision

**Acoustic capture moves to the MPU.** A USB microphone is recorded through `arecord`, health-checked, and
classified by a standing `edge-impulse-linux-runner --run-http-server` process over HTTP — the same
inference transport the vision path already uses (`perception/detector.py`), for the same reason: it is
the one mechanism that needs nothing installed.

Three new modules, mirroring the existing camera/detector split so the seams are where the rest of
`device/mpu` already puts them:

- `perception/microphone.py` — capture only. Discovers the USB card by name (enumeration order is not
  stable across reboots), records 32 kHz mono S16_LE through `plughw:` so ALSA resamples in-kernel, and
  [**corrected to 8 kHz** by the 29 Sept amendment at the end of this ADR]
  measures RMS, peak, clipped fraction and DC offset on every clip.
- `perception/acoustic_detector.py` — the HTTP client. Windows the clip, POSTs raw int16 features, and
  max-pools the windows.
- `services/acoustic_watch.py` — the orchestrator: capture → health → classify → `handle_acoustic_event`.
  It holds no routing logic; what an acoustic class *means* stays settled in `reflex_loop.py`.

`main.py` polls on a daemon thread every `ACOUSTIC_POLL_INTERVAL_S`, gated behind `ACOUSTIC_ENABLED`,
which is **False** until calibration (below) has been run.

**ADR 0009 is narrowed, not superseded.** Its always-on gunshot path remains the right design for the
problem it addresses and remains unbuilt. This ADR replaces the *capture mechanism for the event-gated
acoustic modality*; it does not deliver always-on listening and must not be read as having done so.

### A microphone that lies is worse than one that is absent

The BY-M1 is an electret lavalier powered by one LR44 cell. A dead cell does not unplug the adapter, does
not stop the card enumerating and does not stop frames arriving — it makes them near-silent. Near-silence
classifies as confident `ambient`, which is indistinguishable from a quiet forest.

So every clip is measured and gated **before** inference, and a clip that fails is reported to `fuse()` as
ACOUSTIC *unavailable* — never classified. Fusion can drop a modality that says "I am not here". It has no
defence against one that says "there is nothing here" when the truth is "I cannot tell". The DC-offset
check runs before the silence floor, because an offset inflates RMS and would otherwise mask exactly the
near-silence the floor exists to catch.

The same principle governs unknown labels: a class the deployed impulse emits that `bridge/rpc.py` does
not define maps to *unavailable*, never to `ambient`, so a divergent deploy cannot hide behind a
plausible-looking benign result.

### The health floors are not yet real

`ACOUSTIC_MIN_RMS`, `ACOUSTIC_MAX_CLIPPED_FRACTION` and `ACOUSTIC_MAX_DC_OFFSET` are currently invented,
and marked as such in `services/config.py`. A silence floor is a property of specific hardware in a
specific place; it cannot be derived. `device/mpu/bench/mic_check/mic_check.py calibrate` measures the
microphone switched on and switched off and recommends a floor at the geometric mean of the two — the
midpoint on a log scale, which is the right midpoint for a quantity measured in dB. It refuses to
recommend anything when the two readings are within 12 dB, because below that separation no threshold
distinguishes the states and a number printed anyway would look like a measurement while being a coin
toss.

`ACOUSTIC_ENABLED` stays False until that has been run against the real microphone. This is a deployment
DFO Kothamangalam has approved; an uncalibrated silence floor is not a detail to flip on optimistically.

### Why acoustic polls on its own schedule

Studio's performance estimate for this impulse on the QRB2210 is **4,134 ms** for the PANNs Cnn10 transfer
block alone (float32, unoptimised), with the custom log-mel block unestimated because Studio cannot
profile a custom block. Real per-check cost is that figure times the window count, plus the front end.

Folding an acoustic check into `handle_footfall_event()` — the natural design, where a seismic trigger
wakes both sensors — would drop four-plus seconds of blocking inference into the 45 s vision watch window
ADR 0022 sized to catch an elephant walking 140 m. That is a hole in exactly the window that matters. So
acoustic runs on its own timer and reaches fusion as its own event, and the poll runs on a daemon thread
rather than the main loop because it is not confirmed whether App Lab dispatches `Bridge.provide()`
callbacks on that thread — a deterrence path delayed because the system was busy listening would be worse
than no acoustic modality at all.

## Alternatives considered

- **Register-level SAI, per ADR 0006's finding.** Rejected on fact, not preference: the prebuilt loader's
  devicetree is fixed before the sketch exists, so the peripheral is never clocked. ADR 0006's TrustZone
  analysis was correct about TrustZone and is simply not the binding constraint here.
- **Buy the media carrier board** to get an I2S/SAI header out. Rejected: not purchasable on this
  timeline, and it would not have changed finding (2) — SAI is outside the low-power domain regardless, so
  the always-on property would still not have been delivered.
- **Re-buy the MAX9814 and build ADR 0009 as written.** Not rejected — *deferred*, and it remains the only
  design that delivers always-on gunshot detection. It is orthogonal to this ADR: the analog path wakes
  the system, this path classifies event-gated audio, and the two can coexist. Tracked in
  `docs/KNOWN_GAPS.md`. Note the PANNs model cannot be the MCU-side classifier — it does not fit 786 kB of
  SRAM — so that path still needs its own small model, as ADR 0009 always said.
- **Trigger the acoustic check from a seismic footfall.** Rejected on latency, above.
- **Classify every clip and let fusion weigh a low-confidence result down.** Rejected: this is precisely
  the failure the health gate exists for. A dead microphone does not produce low-confidence `ambient`, it
  produces *high*-confidence `ambient`, and no weighting downstream can recover a distinction that was
  destroyed upstream.
- **Resample on-device from whatever the codec advertises.** Rejected: `librosa` is not installable on the
  board, so `plughw:`'s in-kernel conversion is the only resampler available. This is why the capture rate
  is pinned to the impulse's own 32 kHz rather than being configurable. [**Both halves of this are
  wrong** - the impulse's own rate is 8 kHz and the C++ block does resample. See the 29 Sept
  amendment at the end of this ADR.]

## Consequences

**The `report_acoustic_event` RPC now has no producer.** `bridge/schema.md` still defines it and
`main.py`'s `_on_acoustic_event` adapter still exists, both retained for the deferred MCU gunshot path.
Nothing sends it today. This is the single most confusing thing about the current tree and is called out
in `main.py`'s own docstring for that reason.

**`capture_ref` loses its meaning on this path.** It is documented as an index into the MCU's raw-window
ring buffer; there is no such buffer here. MPU-originated events carry `MPU_CAPTURE_REF = -1` rather than
a plausible-looking `0`, so a log line states something true instead of pointing at a ring slot that was
never written.

**Power.** Event-gated capture on the MPU costs nothing while idle beyond the poll timer, but the MPU must
be awake to run it, so this does not share the geophone's STOP-mode budget. The duty cycle
(`ACOUSTIC_POLL_INTERVAL_S = 30`, ~3 s capture plus ~8 s inference) is the lever, and it is invented
pending a real power measurement.

**Detection profile.** A duty-cycled listener catches sustained sources — a chainsaw, a herd calling —
and is more likely to miss a one-off transient than to hear it. A single gunshot will usually be missed.
That is the honest cost of not having ADR 0009's always-on path, and it is the reason that path stays open
rather than being closed by this decision.

**Latency is the open performance question.** 4,134 ms per window is roughly 30× a vision frame. The
largest available lever is a quantised (int8) variant, which would also revisit ADR 0026 — that ADR's
float32-over-int8 conclusion was reached against the earlier H2 model and does not transfer to PANNs
unexamined.

## Verification

`device/mpu` full suite: **14 failed, 562 passed, 1 skipped** — the identical failure set ADR 0027 records
as pre-existing (boar-gate, `home_test`, night-exposure, schema-version; none acoustic). 50 new tests
across `test_microphone.py` (15), `test_acoustic_detector.py` (21) and `test_acoustic_watch.py` (14) all
pass, and `ruff check` is clean on every file this ADR touches.

The tests that matter most are the negative ones: that a clip failing `assess_health` is never handed to
the classifier, that a capture or inference failure resolves to `available=False` rather than raising into
the reflex path, and that an unroutable label does not become `ambient`.

The model this path calls is not yet deployable, for a reason unrelated to any of the above: Studio
cannot build a native deployment for a project containing a custom DSP block, so the `dsp-panns-logmel`
front end had to be written in C++ by hand. That is now done and verified numerically against the Python
the model trained through — worst disagreement **1.53e-05 dB** across every mel bin of sixteen probe
signals, against a 1e-2 dB tolerance. See `ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/README.md`, which
also documents the export format decision and the App Lab brick drop-in.

**Not yet verified on hardware.** Nothing in this ADR has been run against the real BY-M1 or the real
board. The microphone has not been captured from, the floors are invented, no `.eim` has been built or
executed for the acoustic model yet, and `ACOUSTIC_ENABLED` is False. What is verified is the logic, on a
host.


## Amendment, 2026-09-29: the capture rate in this ADR was wrong, and the port now resamples

Two statements above are incorrect and are corrected here rather than edited away, because the
reasoning that produced them is the interesting part.

**The capture rate is 8 kHz, not 32 kHz.** The Decision section says `perception/microphone.py`
records 32 kHz, and the rejected alternative "Resample on-device from whatever the codec advertises"
justifies that by saying the rate is "pinned to the impulse's own 32 kHz". The impulse's own rate is
8 kHz: it declares `EI_CLASSIFIER_FREQUENCY 8000` with `RAW_SAMPLE_COUNT 80000`, because the corpus is
8 kHz throughout. 32 kHz is the rate PANNs' *filterbank* is defined at, which is not the same thing
and is exactly the confusion this amendment exists to close. Capturing at 32 kHz would not have
skipped a resample; it would have pushed an already-4x-fast signal through the block's own upsample
and landed every frequency in the wrong mel bin, which a PANNs backbone reports as confident wrong
labels rather than as an error. `ACOUSTIC_SAMPLE_RATE_HZ` and `Microphone.SAMPLE_RATE_HZ` are now
8000, with the distinction spelled out at both sites.

**The C++ block resamples.** The premise that "librosa is not installable on the board, so `plughw:`'s
in-kernel conversion is the only resampler available" was true about Python and false about the
deployed path, which is C++. Every window the model has ever seen went through a 4x upsample first -
in training via `dsp.py:147`, and before that via `harness/embed.py`'s `librosa.load(..., sr=32000)`.
A port that refused any rate but 32 kHz was therefore refusing the only rate it will actually be fed.
`panns_logmel_core.hpp` now carries an own-work polyphase Kaiser windowed-sinc for integer upsampling
ratios, designed against the measured response of `librosa.resample`'s default `soxr_hq` rather than
against its documentation - soxr itself is LGPL and cannot be vendored into an MIT tree. Rates that
are not an integer divisor of 32 kHz are still refused.

**Verification of the amendment.** Held to the classifier rather than to decibels: all 605 test clips
scored twice through `cnn10_10s_fp32.onnx`, once resampled by soxr_hq exactly as the harness does it
and once by the port. The reference leg reproduces the published **91.90% (556/605)** exactly, which
is what makes the comparison meaningful; the port returns the same 91.90% with **zero argmax flips**
and a maximum probability delta of 0.063. An earlier candidate that placed the cutoff at soxr's quoted
-0.1 dB point instead of the fitted one scored 91.74% with one flip, so the fit was load-bearing, not
cosmetic. Alongside that: `parity_resample.py` passes at 1.92e-01 dB worst in-band against a 0.5 dB
budget, `parity_cpp.py` is bit-unchanged at 1.53e-05 dB, the C++ filter coefficients match the numpy
design to 1.9e-15, and `panns_logmel.cpp` compiles clean against the real Edge Impulse headers under
`-std=c++14 -Wall -Wextra`.

`device/mpu` full suite after the rate change: **15 failed, 535 passed, 1 skipped, 26 xfailed** - the
same pre-existing set (boar-gate, `home_test`, night-exposure, schema-version, LED clamp), none
acoustic. The 50 acoustic tests were updated to the corrected rate and all pass.

**Still not verified on hardware.** Nothing in this amendment changes that. The BY-M1 has not been
captured from, no `.eim` has been built or executed, and `ACOUSTIC_ENABLED` remains False.
