# App Lab bricks and custom AI models on the UNO Q

How the App Lab application framework actually loads an AI model, written so nobody
on this project has to re-derive it from a stripped binary again.

Every claim is checked against one of three primary sources, named inline so a future
reader can re-check rather than trust:

- **Source** — `arduino/arduino-app-cli` and `arduino/app-bricks-py` on GitHub.
- **Board** — our UNO Q: `arduino-app-cli` / daemon **0.11.0**, assets **0.10.1**.
- **Docs** — `arduino/docs-content` (the markdown behind docs.arduino.cc) and
  docs.edgeimpulse.com.

Where the three disagree, that is said explicitly rather than smoothed over. There
are several places where they do, and two of them have already cost this project a
wrong conclusion in a tracked file.

Link index for everything cited: `app-lab-reference-links.md`.

Captured 30 September 2026.

---

## 1. Four objects, and which one you are configuring

Most confusion here comes from collapsing four separate things:

| Object | What it is | Where it lives |
|---|---|---|
| **App** | Your program plus its manifest | `~/ArduinoApps/<app>/`, described by `app.yaml` |
| **Brick** | A reusable capability: a Python package, optionally with its own containers | `arduino.app_bricks.<name>`, described by `brick_config.yaml` |
| **Model** | The weights — an `.eim` blob | `~/.arduino-bricks/models/<id>/`, described by `model.yaml` |
| **Runner** | The container that loads the blob and serves HTTP | `ghcr.io/arduino/app-bricks/ei-models-runner`, described by `brick_compose.yaml` |

The separation is deliberate: *"there is a strict separation between AI Bricks (the
Python interface and Docker Runner) and AI Models (the data blobs/weights)"* (Docs,
custom-bricks).

So "deploying a model" is three independent facts, and they fail independently:

1. The blob exists on disk and the runner can load it.
2. The daemon has **registered** it — it appears in the models index and in the
   brick's `compatible_models`.
3. An app has **bound** it — some `app.yaml` names it, and that app is running.

**Registered is not running.** Our acoustic model sat at state 2 for a while and an
earlier revision of `HANDOVER.md` reported it as deployed and working. Keep the three
numbered when writing status anywhere.

---

## 2. `app.yaml` — the application manifest

### Schema

Authoritative definition, `internal/orchestrator/app/parser.go` (Source):

```go
type Brick struct {
	ID        string            `yaml:"-"` // handled by a custom unmarshaller
	Model     string            `yaml:"model,omitempty"`
	Variables map[string]string `yaml:"variables,omitempty"`
	Devices   []string          `yaml:"devices,omitempty"`
}

type AppDescriptor struct {
	Name        string  `yaml:"name"`
	Description string  `yaml:"description"`
	Ports       []int   `yaml:"ports"`
	Bricks      []Brick `yaml:"bricks"`
	Icon        string  `yaml:"icon,omitempty"`
	// Deprecated: use the per-Brick Devices field instead.
	RequiredDevices []string `yaml:"required_devices,omitempty"`
}
```

That is the whole manifest. There is **no `version` key** and **no app-level
`environment` key**; both have been guessed at in this repo before.

`icon` is validated, not cosmetic: `IsValid()` rejects anything that is not a single
emoji, so a plain string there fails the parse.

### Both brick syntaxes are legal

`Brick.UnmarshalYAML` accepts two node types, and this is the single most misleading
thing in the system:

```yaml
bricks:
  # ast.StringType - a bare ID
  - arduino:web_ui

  # ast.MappingType - single key, value carries the options
  - arduino:audio_classification:
      model: etx-acoustic-panns-20260930
      variables:
        SOME_DECLARED_VAR: "value"
      devices:
        - microphone
```

All ~25 stock example manifests on the board use the flat form, because none of them
override a model. Reading those and concluding that `model` is not a key is exactly
the mistake this project made — the tag is right there in the struct. The matching
`MarshalYAML` always writes the mapping form, which is why App Lab rewrites a
manifest into mappings the first time its UI touches it.

### The UI owns this file

*"App Lab automatically saves these settings to your `app.yaml` file, and passes them
to the Brick as environment variables when the App runs"*, and *"Manual changes can
cause syntax errors that prevent the editor from opening your project"* (Docs,
use-bricks).

For most apps the right move is to never hand-edit it. Ours is an exception, because
App Lab's regeneration drops the golden-compose additions the watchdog re-applies
(see `HANDOVER.md`). Knowing the schema is what makes that exception maintainable.

---

## 3. `brick_config.yaml` — the brick manifest

Full schema (Docs, bricks-reference):

```yaml
id: "arduino:object_detection"   # arduino: prefix for official; folder name for custom
name: "Object Detection"
description: "Detects objects using AI"
category: "video"                # miscellaneous | video | audio | text | UI | Storage
requires_display: webview        # tells App Lab to open a webview on start
required_devices:                # <-- VALIDATED AT APP STARTUP
  - camera
ports:
  - 7000
variables:                       # injected as environment variables
  - name: "THRESHOLD"
    default_value: "0.5"
    hidden: false                # true = not shown in the UI
    secret: false                # true = masked in the UI
supported_boards: [unoq, ventunoq]
requires_services: ["arduino:genie"]
mount_devices_into_container: true
```

Two fields deserve attention:

- **`required_devices` is enforced.** *"When the app is started, the
  `arduino-app-cli` performs startup validation to ensure at least one physical
  device of that class is currently connected to the board. If not, an error is
  raised."* Declaring `microphone` means the app will not start without one — useful,
  and a trap if you bind a brick before the hardware lands.
- **`variables` are only the ones the brick declares.** A brick's `variables:` block
  in `app.yaml` cannot carry arbitrary environment variables — only names from that
  brick's own `brick_config.yaml`. Our `ELETECT_*` variables therefore live in the
  golden compose, not in the manifest.

### The audio brick, as shipped

`app-bricks-py`, `src/arduino/app_bricks/audio_classification/brick_config.yaml`:

```yaml
id: arduino:audio_classification
category: audio
ai_frameworks_compatibility: [edgeimpulse]
model: glass-breaking                      # the default when app.yaml omits `model`
model_configuration_variables:
  - EI_AUDIO_CLASSIFICATION_MODEL          # which var a selected model may write
variables:
  - name: EI_AUDIO_CLASSIFICATION_MODEL
    hidden: true
    default_value: /models/ootb/ei/glass-breaking.eim
  - name: CUSTOM_MODEL_PATH
    hidden: true
    default_value: /home/arduino/.arduino-bricks/ei-models
  - name: BIND_ADDRESS
    hidden: true
    default_value: 127.0.0.1
```

`model_configuration_variables` is the hinge: it names which environment variable a
selected model is allowed to set. That is why a model descriptor's
`model_configuration` block works at all.

Note what is **absent**: no `required_devices`. The audio brick does *not* declare a
microphone, so binding it will not fail startup on a board with no mic — it will fail
later, at capture time.

---

## 4. `model.yaml` — the model descriptor

Schema, `modelsindex/custommodel/parser.go` (Source):

```go
type ModelDescriptor struct {
	ID          string            `yaml:"id"`
	Name        string            `yaml:"name"`
	Runner      string            `yaml:"runner"`
	Description string            `yaml:"description"`
	Bricks      []BrickConfig     `yaml:"bricks"`
	Metadata    map[string]string `yaml:"metadata,omitempty"`
}

type BrickConfig struct {
	ID                 string            `yaml:"id"`
	ModelConfiguration map[string]string `yaml:"model_configuration,omitempty"`
}
```

### Registration is two files

The models index scans a directory for any subdirectory containing a `model.yaml` and
loads the descriptor next to the blob. That is the entire contract:

```
~/.arduino-bricks/models/<model-id>/
    model.eim      the blob
    model.yaml     the descriptor
```

No daemon call, no API key, no upload.

### `metadata.source: edgeimpulse` switches on a validator

From `Validate()` / `validateEdgeImpulseMetadata()` (Source). Setting that one key
makes all of the following mandatory:

| Field | Requirement |
|---|---|
| `ei-project-id` | non-empty |
| `ei-impulse-id` | non-empty |
| `ei-impulse-name` | non-empty |
| `ei-deployment-version` | non-empty |
| `ei-model-type` | exactly `float32` |
| `ei-engine` | exactly `tflite` |

`id` and `name` are required unconditionally. Omit `source` entirely and none of the
EI fields are checked — worth knowing, though we set it because the model genuinely
came from Edge Impulse.

The `ei-model-type: float32` rule is a hard constraint on the int8 question tracked in
ADR 0030: an int8 `.eim` cannot be registered through this path while declaring
`source: edgeimpulse`.

### A discrepancy, unresolved

Our descriptor sets `runner: "brick"`, `runner` is a real yaml tag, and yet
`arduino-app-cli model list --format json` reports `"Runner": ""` for our model.
Everything else (`id`, `name`, `description`, `bricks`, `metadata`) round-trips
correctly and the model works, so this looks like a listing-layer artefact in 0.11.0
rather than a defect in the file. Noted, not chased.

### Custom bricks declare models differently

A custom brick ships a `models-list.yaml`, and the shape is a keyed mapping rather
than a flat `id:` (Docs, custom-bricks):

```yaml
models:
  - my-model:
      runner: brick
      name: "Custom Model"
      bricks:
        - id: "my_custom_brick"
      metadata:
        ei-project-id: 12345
        ei-model-url: "https://studio.edgeimpulse.com/public/12345/live"
```

Here `ei-model-url` makes the orchestrator **download** the `.eim`. Do not confuse
this file with `model.yaml`; different schemas, different jobs.

---

## 5. Runners, ports, and how the Python client finds them

### The port map

Every EI brick publishes a distinct host port onto container `1337` (read from each
brick's `brick_compose.yaml` on the board):

| Brick | Compose service | Host port |
|---|---|---|
| `object_detection` | `ei-obj-detection-runner` | 1337 |
| `image_classification` | `ei-classification-runner` | 1338 |
| `audio_classification` | `ei-audio-classifier-runner` | **1339** |
| `keyword_spotting` | `ei-keyword-spot-runner` | 1340 |
| `motion_detection` | `ei-motion-detection-runner` | 1341 |
| `vibration_anomaly_detection` | `ei-anomaly-detection-runner` | 1342 |
| `visual_anomaly_detection` | `ei-obj-video-anomalies-det-runner` | 1343 |

Two consequences for us:

- Our host-side bare runner listens on **1338**, which is `image_classification`'s
  port. It is free only because we do not run that brick. If it is ever added, our
  default has to move.
- A "spare port for testing" must come from outside 1337–1343. An earlier
  verification recipe in `ml/acoustic/TUTORIAL.md` used 1340, which is
  `keyword_spotting`'s.

### The app never uses the host port

`arduino/app_internal/core/ei.py`, `_get_ei_url()` (Board):

```python
infra = load_brick_compose_file(cls)
host = next(iter(infra["services"]))     # first service key = the hostname
addr = resolve_address(host)
return f"http://{addr}:1337"
```

The client reads the brick's own compose file, takes the **first service name** as a
DNS hostname, and always talks to **1337** on the Compose network. The published host
port exists so a human can `curl` it. This matches the documented rule: *"your Python
code must communicate with the containerized service over the virtual Docker Compose
network ... using the service name defined in your `brick_compose.yaml` as the
hostname"* (Docs, custom-bricks).

So once the brick is bound our correct endpoint is
`http://ei-audio-classifier-runner:1337` — not 1339, and not `127.0.0.1` anything.
This is the same constraint that forced the vision runner host-side: the App Lab
container cannot reach the host's loopback over the bridge network.

### Compose files differ by board

Each brick ships `brick_compose.yaml` and `brick_compose.ventunoq.yaml`. The UNO Q
variant runs `ei-models-runner`; the VENTUNO Q variant runs `ei-qnn-models-runner`
with `dma_heap`/`fastrpc` devices for the NPU.

The official model catalogue corroborates that there is no NPU path for us: every
model described as *"optimized for NPU acceleration"* is listed **VENTUNO Q only**,
while the UNO Q entries are plain CPU builds (Docs, integrations/models). Consistent
with the `uno-q-gpu-acceleration-ceiling` finding — CPU int8 is the ceiling.

---

## 6. Getting a custom model onto the board

### Route A — App Lab's Edge Impulse import (the supported one)

Docs, ai-models:

1. Add the brick to an app.
2. Open the brick's **AI models** tab → **Train new AI model**.
3. Pair the Arduino account with Edge Impulse (same login).
4. Build the impulse in Studio, test it.
5. Return to App Lab; the model appears in the brick's model list.
6. **Install** — App Lab builds and downloads the `.eim` to the board.
7. **Brick configuration** → select the model → Save.

Step 7 is what writes `model:` into `app.yaml`.

**This route is permanently closed for our acoustic model.** The importer hardcodes
the deployment target for board `unoq` to `{float32, tflite, runner-linux-aarch64}`
and asks Studio to build one if missing. Studio refuses:

```
Cannot build for "runner-linux-aarch64" as your project contains custom DSP blocks.
Use the C++ library export option and build locally.
```

Our PANNs log-mel front end is an organisation DSP block, so the refusal stands as
long as the impulse keeps it. Verified against Studio, build job 54315745, project
1110036 impulse 19.

Two community reports look like this failure and are not:

- **EI forum 18577** — App Lab filters which EI projects it offers by impulse
  metadata; a non-standard impulse simply is not listed. The workaround found there
  was a Transfer Learning (Keyword Spotting) block, 1000 ms window, 16 kHz, MFE.
  That is the *stock* shape, and the 1000 ms cap is one of the three walls in
  `ml/acoustic/TUTORIAL.md` §3 — our audio needs longer windows, so that workaround
  is closed to us too.
- **Arduino forum 1447504** — a custom model was installed but the brick silently
  served the built-in one: *"Custom edge Impulse model wasn't correctly configured
  for `arduino:video-object-detection` brick."* Fixed in **arduino-app-cli 0.11.1**,
  and the fix requires deleting the model from the board and re-downloading it. Our
  board runs **0.11.0** — the version with the bug. We register by hand rather than
  through the importer, so we are probably not exposed, but "probably" is doing work
  in that sentence: verify serving rather than assume.

### Route B — register a locally built `.eim` (what we do)

Write the two files from §4 and the daemon picks the model up. Then confirm properly:

```sh
# 1. the models index knows it
arduino-app-cli model list
#   etx-acoustic-panns-20260930   EleTect-X acoustic (PANNs Cnn10)

# 2. the BRICK knows it - this is the one that matters, because it is the same
#    list the UI's model picker reads
arduino-app-cli brick details arduino:audio_classification --format json
#   "compatible_models": [ {"id": "glass-breaking", ...},
#                          {"id": "etx-acoustic-panns-20260930", ...} ]
```

Check 2 is the meaningful one. A `model.yaml` whose `bricks:` entry names a brick that
does not exist still lists under `model list` and will never reach the app.

### Route C — point the brick at a path, skipping the registry

Edge Impulse documents an older App Lab workflow (0.1.23) that binds the `.eim`
directly through the brick's variables, with no model registration at all:

```yaml
name: Faces Detector
bricks:
- arduino:video_object_detection: {
    variables: {
      EI_OBJ_DETECTION_MODEL: /home/arduino/.arduino-bricks/ei-models/<modelname>.eim
    }
  }
```

The per-brick variable names (Docs, EI run-arduino-app-lab):

| Brick | Model variable |
|---|---|
| `audio_classification` | `EI_AUDIO_CLASSIFICATION_MODEL` |
| `image_classification` | `EI_CLASSIFICATION_MODEL` |
| `keyword_spotting` | `EI_KEYWORD_SPOTTING_MODEL` |
| `motion_detection` | `EI_MOTION_DETECTION_MODEL` |
| `object_detection` | `EI_OBJ_DETECTION_MODEL` |
| `visual_anomaly_detection` | `EI_V_ANOMALY_DETECTION_MODEL` |

EI calls this legacy and superseded, and it is — but it still works, because those
variables are exactly what the compose file interpolates. It is the fallback if
registration ever misbehaves, and it also confirms independently that
`/home/arduino/.arduino-bricks/ei-models/` was never an invented path.

One catch if you use it: you must also set `CUSTOM_MODEL_PATH`, because that is what
the volume mount interpolates. Its declared default in `bricks-list.yaml` is
`.../ei-models`, which would not cover a model stored anywhere else.

### Verifying the runner serves it, without restarting the app

Run the brick's own image with exactly the arguments its compose file passes, on a
port outside 1337–1343:

```sh
D=/home/arduino/.arduino-bricks/models/etx-acoustic-panns-20260930
docker run --rm -d -p 127.0.0.1:1400:1337 -v "$D:$D" \
    ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0 \
    --model-file "$D/model.eim" --run-http-server 1337 --dont-print-predictions

curl -s http://127.0.0.1:1400/api/info
```

Same image, same model, same command line — only the published port differs, so the
result transfers to the bound brick.

---

## 7. Custom bricks

Worth knowing even though we do not ship one, because it is the escape hatch if the
stock audio brick stops fitting.

```
my-app/
├── app.yaml
├── python/main.py
└── bricks/
    └── my_custom_brick/        # folder name == brick ID, no `arduino:` prefix
        ├── __init__.py         # Python logic
        ├── brick_config.yaml   # required
        ├── brick_compose.yaml  # optional
        ├── models-list.yaml    # optional, for EI models
        └── requirements.txt    # optional
```

The constraints that decide whether this is viable:

- **Your brick's Python runs in the *main app* container**, not in the containers
  your `brick_compose.yaml` defines. Cross the gap over HTTP using the service name.
- **No `build:` directive.** App Lab cannot build an image from a Dockerfile on the
  board. Publish to a public registry, or `docker load` it manually.
- **No private registries** for custom brick images.
- **Models and images are not exported** with the app; only source is.
- `bricks/` is added to `sys.path` automatically, so `from my_custom_brick import ...`
  works in `main.py`.

### Lifecycle

Decorate with `@brick` and let `App.run()` drive it. The orchestrator discovers
`start()` (once), `stop()` (once, on shutdown), `loop()` (repeatedly, own thread) and
`execute()` (once, own thread); `@brick.loop` and `@brick.execute` tag arbitrary
method names for the same treatment.

`App.run()` blocks, so all setup goes above it. Do not call `start()` yourself —
instantiating the class is what registers it.

---

## 8. Using the audio brick from Python

```python
from arduino.app_utils import App
from arduino.app_bricks.audio_classification import AudioClassification

ac = AudioClassification(confidence=0.6)
ac.on_detect("elephant_call", lambda: alert())

App.run()
```

Verified against the installed package in the app container:

```
AudioClassification.__init__(self, mic: Microphone = None, confidence: float = 0.8)
```

Both arguments default, so it finds the microphone itself. Public methods:
`on_detect`, `classify_from_file(audio_path, confidence=0.8)`, `infer_from_file`,
`infer_from_image`, `process`, `start`, `stop`.

`classify_from_file` needs no microphone and is the quickest smoke test of a freshly
registered model.

**Naming trap.** The brick's shipped `docs/.../audio_classification/README.md` — the
text `arduino-app-cli brick details` also returns — says:

```python
from arduino.app_bricks.audio_classifier import AudioClassifier   # WRONG
```

That module does not exist. The installed package, both in the app container's
site-packages and in `arduino/app-bricks-py`, is `audio_classification`, exporting
`AudioClassification`. The prose README is stale; the generated `API.md` is correct.

---

## 9. Version state, and what our board is missing

| Component | Ours | Upstream (30 Sep 2026) |
|---|---|---|
| `arduino-app-cli` / daemon | **0.11.0** | 0.13.0 stable, 0.14.0-rc.3 |
| App Lab assets bundle | **0.10.1** | — |
| `ei-models-runner` image | **0.10.0** | 0.13.0 |

Roughly two minor versions behind. What that costs, from upstream release notes and
the audio brick's current `brick_compose.yaml`:

- **0.11.1** — the custom-model-not-selected fix from Arduino forum 1447504.
- **0.13.0** — *"PipeWire audio is available to the Python runner: its socket is
  mounted into the app container."* Directly on the acoustic critical path.
- **0.13.0** — pre-run checks: apps verify that the models their bricks need are
  installed and compatible, and that mount paths exist. That would have caught our
  registration state automatically.
- **Current runner compose** adds a second mount,
  `/var/lib/arduino-app-cli/models/edge-impulse`, plus log rotation (`max-size: 5m`,
  `max-file: 2`). Our 0.10.1 compose has neither, and that directory does not exist
  on our board.

**This is not a recommendation to upgrade today.** The board runs a production
deterrence stack behind a hand-merged golden compose and a watchdog, there is no
passwordless sudo, and an App Lab upgrade regenerates app compose files. If done it
should be a planned maintenance window with the golden compose captured first, not an
incidental step. The upside is real; so is the blast radius.

The PipeWire gap does **not** block us — see §10.

---

## 10. Audio on this board, measured

Checked on the board rather than assumed, because the 0.13.0 PipeWire note implied
audio might not reach the app container at all on 0.11.0.

**Host capture devices** (`/proc/asound/cards`):

```
0 [ArduinoImolaHPH]: qcm2290 - Arduino-Imola-HPH-LOUT
1 [Camera        ]: USB-Audio - USB 2.0 Camera
```

Card 1 is the USB webcam's microphone. A caution on identifying it: ALSA prints
`Arducam Technology Co., Ltd.` because that string is in the USB descriptor, but
`lsusb` reports `0c45:6366 Microdia Webcam Vitade AF`. It is a Vitade webcam and the
descriptor's manufacturer string is misleading — trust the VID:PID. It advertises a
mono S16_LE capture endpoint at 8000–48000 Hz.

**The app container can already use it.** `/dev` is bind-mounted wholesale by our
golden compose, so `/dev/snd` is present and `arecord` is installed:

```sh
docker exec eletect-x-main-1 \
  arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 3 /tmp/cap.wav
```

Two 2-second captures gave RMS 2380 and 2573, DC offsets of −204 and +1334, and
0.01–0.02 % clipped samples — varying, structured ambient noise, not a railed or
floating input. 16 kHz mono is exactly the model's input format.

The PipeWire socket at `/run/user/1000/pipewire-0` is **not** mounted into the
container, which is the 0.13.0 feature we lack. It does not matter here: raw ALSA
works and is what we would use anyway.

**What this changes.** The acoustic path can be integration-tested end to end now,
against a real microphone, before the BY-M1 arrives. The BY-M1 is still required for
deployment — directionality, weather sealing, and a sane gain structure; this one
runs hot — but it is no longer a blocker on *testing*, only on *fielding*. That
distinction was previously collapsed in our status docs.

---

## 11. Two landmines in the running container

Found while verifying the above, via `docker inspect eletect-x-main-1`. Both are live
in the golden compose today:

- **`HOST_IP=192.168.1.5`** — the board is `192.168.1.4`.
- **`VIDEO_DEVICE=/dev/video0`** — `/dev/video0` is the **Qualcomm Venus hardware
  video decoder** (`qcom-venus`), not a camera. The USB camera is `/dev/video2`
  (`uvcvideo`, "USB 2.0 Camera"). There are six `/dev/video*` nodes; only some are
  capture devices.

Neither is currently breaking anything visible, which is precisely why they are worth
recording: vision runs today, so whatever consumes the camera is not taking its device
from `VIDEO_DEVICE`. Both should be corrected in the same maintenance window as any
brick binding, and the correction verified by `docker inspect` afterwards rather than
by reading the compose file.

---

## 12. Corrections this research forced

Recorded because two were wrong in tracked files, and one had already been
"corrected" once in the wrong direction.

1. **`model:` IS a valid `app.yaml` key.** A previous revision of
   `ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/README.md` asserted the opposite on
   two pieces of evidence: the stock examples all use flat ID strings, and a grep of
   the stripped binary found no `yaml:"model"`. The first observation is true but the
   inference from it is not — `UnmarshalYAML` accepts both shapes. The second was a
   grep artefact: the tag is stored as `yaml:"model,omitempty"`. Fixed.
2. **The brick's Python module is `audio_classification`, class
   `AudioClassification`** — not `audio_classifier` / `AudioClassifier` as the
   brick's own shipped README says. Fixed in `ml/acoustic/TUTORIAL.md` §8.4.
3. **Do not call `start()` on a brick.** `@brick` registers the instance on
   construction; `App.run()` drives the lifecycle.
4. **1338 is `image_classification`'s port**, not a neutral choice, and 1340 is
   `keyword_spotting`'s — so it is not a safe "spare" for testing.
5. **A microphone is already attached.** Status text treating the BY-M1 as blocking
   all acoustic work overstates it; it blocks fielding, not testing.

---

## 13. Where Edge Impulse's own App Lab reference material is wrong or thin

Edge Impulse publishes a condensed App Lab reference alongside its docs. It is
useful but it is **not** a substitute for sections 2-6 above, and in three places
it will actively mislead. Checked against upstream on 30 September 2026.

- **It documents only Route C.** Its `app.yaml` example is
  `- arduino:video_object_detection: {}` and its model advice is "set
  `EI_OBJ_DETECTION_MODEL` in `app.yaml` bricks variables". The `model:` key, the
  `~/.arduino-bricks/models/<id>/model.yaml` registry, and `arduino-app-cli model
  list` do not appear at all. Route B is the current supported mechanism.
- **Its env-var table lists `EI_IMAGE_CLASSIFICATION_MODEL`**, which is not in Edge
  Impulse's own list; the documented name for that brick is `EI_CLASSIFICATION_MODEL`.
  Treat that table as the unreliable one.
- **Nothing on the port map**, or on `_get_ei_url()` resolving to container 1337 via
  the compose service name.

Two things in it that *are* worth keeping and are not in the Arduino docs:

- `.eim` files must be `chmod +x`, and must be the `linux-aarch64` build. A model
  copied with `scp` arrives non-executable and fails with no useful error.
- Port **7000 is reserved for the App Lab IDE / `web_ui` brick**; 5001 is the
  suggested port for a Flask app. Ours is on 8090, clear of both.

Both corrections are worth reporting upstream.

---

## 14. CLI facts that matter operationally

From the generated command reference (Docs, cli/commands), checked against our
0.11.0 binary.

### The upgrade path

```sh
arduino-app-cli system update --only-arduino    # Arduino packages only
arduino-app-cli system update --yes             # non-interactive
```

This is how 0.11.0 to 0.13.0 would happen. `--only-arduino` limits the blast radius
to Arduino packages rather than the whole Debian system, which is the flag to use if
the upgrade in section 9 is ever approved. It needs root, so an operator runs
it interactively.

### `app clean-cache` would destroy the golden compose

```sh
arduino-app-cli app clean-cache <app-id> [--force]   # --force works on a RUNNING app
```

Our `.cache/app-compose.golden.yaml` — the hand-merged compose carrying the 8090
publish and every `ELETECT_*` variable — lives in exactly the directory this command
deletes. `--force` removes the guard that the app is running.

**Never run `app clean-cache` on `user:eletect-x`** without first copying
`.cache/app-compose.golden.yaml` off the board. The watchdog re-applies the golden
compose, but it re-applies a file that would no longer exist.

### Reclaiming disk

```sh
arduino-app-cli system cleanup    # removes unused/obsolete app images
```

The supported equivalent of the manual `docker image prune` done on 30 September.
Prefer this next time.

### Startup app, from the CLI

```sh
arduino-app-cli properties get default
arduino-app-cli properties set default /home/arduino/ArduinoApps/eletect-x
arduino-app-cli properties set default none      # unset
```

Only one app can be the startup app; setting a new one silently replaces the previous.

### Other commands worth knowing

```sh
arduino-app-cli app logs <path> --follow --tail 100
arduino-app-cli app export <path> [out.zip] --include-data --overwrite
arduino-app-cli app new <name> -b <bricks> --no-sketch --from-app <path>
arduino-app-cli model delete <model_id> [--force]   # --force deletes a model in use
arduino-app-cli app list --show-broken-apps
arduino-app-cli daemon --port 8080
```

App paths accept the `user:` and `examples:` shorthands (`app start user:eletect-x`).
`--format json` is global, not per-command.

Note `arduino-linux-config`, added in 0.8.0 for media-carrier support — a second CLI
that exists on the board and is not documented alongside `arduino-app-cli`.

---

## 15. Bridge constraints, and one thing we do against the documentation

The Bridge API reference (Docs, bridge/bridge-api) states limits that this repo has
already recorded once, in `README.md` section 5 of this same folder. They are repeated
here with their primary-source wording because the rule is written down and the
firmware does not follow it.

### Hard limits

Confirmed against the official reference, matching what `README.md` section 5 already
states:

- Linux side `/dev/ttyHS1`, MCU side `Serial1`, **115200 bps**.
- **Maximum message size 256 bytes.** `Bridge.notify()` silently *drops* an oversized
  message; the Python `Bridge.call()` raises `ValueError`. The silent drop is the
  dangerous one — `report_footfall_event` and `send_lora_event` are both
  notify/provide traffic, and a payload that grew past 256 bytes would fail
  invisibly.
- `arduino-router` holds an exclusive lock on those interfaces. Opening `/dev/ttyHS1`
  or `Serial1` from application code breaks the Bridge.

### `provide()` versus `provide_safe()`

Quoting the reference:

> `provide()` — "The provided function executes in the high-priority background RPC
> thread. Functions registered with this method must remain short and thread-safe."

> `provide_safe()` — "ensures it executes within the main `loop()` context.
> Applications use this method if the callback function interacts with standard
> Arduino APIs, such as `digitalWrite` or `Serial`, to prevent concurrency crashes."

> **Danger:** "Do not use `Bridge.call()` or `Monitor.print()` inside functions
> registered with `Bridge.provide()`. Initiating a new communication while responding
> to one causes system deadlocks."

`device/mcu/src/main.cpp` registers `drive_horn`, `drive_led`, `pulse_ir` and
`send_lora_event` with plain `Bridge.provide()`. Tracing `bridge_drive_horn` into
`drive_horn()` and `horn_fire_sequence()`, that callback:

- calls `digitalWrite(HORN_AMP_ENABLE_PIN, ...)`,
- switches 74HC4053 UART ownership via `uart_share_acquire()`,
- writes DFPlayer AT commands over the shared UART,
- and calls `delay(HORN_AMP_ENABLE_DELAY_MS)` and `delay(duration_ms)`.

So it is neither short nor confined to thread-safe operations, and it blocks the
high-priority RPC thread for the whole burst. `bridge_handlers.cpp` additionally calls
`Serial.print()` from `log_schema_mismatch()` inside these callbacks — and since
Zephyr core 0.55.0 routes `Serial` to the Serial Monitor, that is the `Monitor.print()`
the danger note names. It fires only on a schema mismatch, which is precisely the
error path where losing diagnostics to a deadlock would hurt most.

Our own `README.md` section 5 already says *"Use `Bridge.provide_safe()` for handlers
that touch Arduino I/O (`digitalWrite` etc.)"* and *"Never call `Bridge.call()` /
`Serial.print()` / `Monitor.print()` inside a `Bridge.provide()` callback"*. So this is
not a newly discovered platform rule — it is a rule we documented and then did not
apply in `device/mcu`. Worth stating plainly, because a documented-but-unapplied rule
reads as a solved problem in every later review.

**This is not currently failing in the field**, which is why it is written down rather
than changed here. Moving to `provide_safe()` defers actuation to the next `loop()`
iteration, which changes deterrence latency — a frozen-architecture concern needing an
ADR and a measured latency comparison, not an incidental edit. Recommended as its own
piece of work.

There is also existing evidence that this area is fragile: `get_system_state` is
commented out in `main.cpp` with a note that registering an additional
`Bridge.provide()` has broken things before. That is consistent with RPC-thread
contention rather than with a registration limit, and `provide_safe()` is the
documented remedy.

### MsgPack type mapping

| Python | C++ |
|---|---|
| `bool` | `bool` |
| `int` | `int8_t` ... `uint32_t` |
| `float` | `float`, `double` |
| `str` | `char*`, `String` |
| `list` | `std::vector`, `std::array`, `std::list` |
| `dict` | `std::map` |
| `bytes` | `std::vector<uint8_t>`, `arduino::msgpack::arr_t<uint8_t>` |
| `None` | `void` |

`Monitor.read()` returns `0` rather than `-1` on an empty queue, contrary to the
`Stream` contract — do not port stock Arduino code that tests for `-1`.

---

## 16. Smaller facts worth not re-deriving

- **`requirements.txt` goes in `python/`**, not the app root. `uv` installs it at Run.
- **`sketch/sketch.yaml` is mandatory whenever a sketch exists**, and App Lab writes it
  when you add a library through the UI.
- **`App.run(user_loop=fn)`** takes an optional loop callback. Code after `App.run()`
  never executes.
- **One app runs at a time**, and only one app can be the startup app.
- Since Zephyr core 0.55.0, `Arduino_RouterBridge` is included by default and `Serial`
  works without manual includes.
- App descriptions fall back to `README.md` when `app.yaml` has no `description`
  (0.6.0), so our empty `description` is not invisible in the UI.
- Supported boards are UNO Q 2 GB, UNO Q 4 GB and VENTUNO Q. FQBN `arduino:zephyr:unoq`.
- Containerised bricks need internet on **first** deployment only, to pull images.
- There are 29 official bricks. The audio path could also use `keyword_spotting`
  (a different brick with its own runner on 1340) — it is the one the EI forum
  workaround uses, and it is capped at a 1000 ms window.
- App Lab's own AI assistant ("Agent Mode") is unrelated to any of this and has no
  bearing on how models are bound.

---

## 17. Network, firewall and host-setup facts

From Docs `configure/network-configuration`, `configure/config`, `configure/settings`
and `setup/{windows,macos,linux,standalone}`. Most of the setup pages are host-install
procedure with nothing for us, but four items below bear directly on fielding a board
at Kothamangalam.

### Outbound domains the board needs

A brick's container image is pulled on **first deployment only**, and the pull does not
come from a single registry:

| Domain | What needs it |
|---|---|
| `downloads.arduino.cc` | system updates, toolchains, library indexes |
| `apt-repo.arduino.cc` | Arduino Debian packages |
| `public.ecr.aws` | Docker images for App Lab bricks |
| `github.com`, `raw.githubusercontent.com` | source and package retrieval |
| `app.arduino.cc`, `login.arduino.cc` | Arduino Cloud sign-in |
| `time.nist.gov` | NTP |

Note our own runner is `ghcr.io/arduino/app-bricks/ei-models-runner`, which is a third
registry again. **Any image pull must happen before the board goes to the field** — a
tethered or metered forest link should not be the first thing that tries to fetch a
container image.

### Ports

| Port | Proto | Service |
|---|---|---|
| 5353 | UDP | mDNS board discovery |
| 22 | TCP | SSH — this is how Network Mode deploys apps |
| 80 / 443 | TCP | updates, images, API |
| 123 | UDP | NTP |
| 7000 | TCP | WebUI brick default — **overridable when the brick is initialised** |

NTP matters more than it looks: event timestamps are what the dashboard orders alerts
by, and the QRB2210 has no battery-backed RTC. A board that boots without reaching
`time.nist.gov` or port 123 will timestamp events from a bogus clock.

### SSH is on by default, and that is a deployment-bar question

Settings exposes **Remote access (SSH)** as a toggle, **enabled by default**, using the
`arduino` user's Linux password. The same password gates Network Mode, SSH and the SBC
desktop login. For a box mounted unattended in a forest on a shared uplink, that is one
shared password on an internet-reachable service, and it is worth deciding deliberately
rather than inheriting the default. Not changed here — it would lock us out of our own
remote access path, so it needs a deliberate decision first.

### Field Wi-Fi limits

- **Captive portals are not supported** by the setup wizard. Any network with a
  web login or "Agree" page cannot be joined through App Lab.
- **WPA2-Enterprise** works, but only via `nmcli` by hand — the wizard will not do it.
- WPA/WPA2 Personal is the only natively supported case.

### Host-side, for the record

The Linux `udev` rule App Lab installs matches two vendor IDs — `2341` (Arduino) and
`05c6` (Qualcomm) — which is the host-side confirmation that the board enumerates as a
Qualcomm USB device as well as an Arduino one. Windows additionally needs
`mdns-discovery.exe` allowed through Defender or the board never appears in Network
Mode. Apple USB-C Digital AV Multiport Adapters are called out as incompatible in SBC
mode. None of this affects the deployed board; it affects whoever sets up a laptop next.
