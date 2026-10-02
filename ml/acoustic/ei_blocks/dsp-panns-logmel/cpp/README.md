# Deploying the PANNs acoustic impulse to the UNO Q

This directory holds the C++ implementation of the `dsp-panns-logmel` custom
processing block, plus the harness that proves it matches the Python the model
was trained through.

It exists because of one sentence in the Edge Impulse documentation, and
everything below follows from it.

## Why a cloud deployment does not work

Studio cannot build a deployment for a project containing a custom DSP block.
Selecting **UNO Q** — or any other native target — fails in about fifteen
seconds with:

```
Cannot build for "arduino-uno-q" as your project contains custom DSP blocks
```

`type=runner-linux-aarch64` fails identically. The reason is documented, not a
bug:

> we cannot automatically generate optimized native code for the block, like we
> do for built-in processing blocks.

A custom block is Python running in a container during training and testing.
There is no Python on the inference path, so somebody has to write the C++. Edge
Impulse's sanctioned mechanism for that is the `cppType` field in
`parameters.json`:

```json
"cppType": "panns_logmel"
```

With that set, the **C++ library** export emits into
`model-parameters/model_variables.h`:

- a populated `ei_dsp_config_panns_logmel_t` carrying the block's parameters, and
- a *forward declaration only* of

```c
int extract_panns_logmel_features(signal_t *signal,
                                  matrix_t *output_matrix,
                                  void *config_ptr,
                                  const float frequency);
```

Supplying the body is the integrator's job. [`panns_logmel.cpp`](panns_logmel.cpp)
is that body.

So the export still originates from Edge Impulse — the model, the weights, the
DSP parameters and the whole inferencing SDK all come out of Studio. What Studio
cannot generate is this one function, and this directory supplies it.

## What format the audio model is exported in

Three formats are on the table for this project. Only the third is usable here.

| Export | What it is | Usable? |
| --- | --- | --- |
| **UNO Q** (native) | prebuilt `.eim` from Studio's build farm | **No** — blocked by the custom block, as above |
| **TensorFlow Lite** | bare `.tflite` of the learning block only | **No** — the log-mel front end is not in it, so it would have to be reimplemented *and* wired up by hand anyway |
| **C++ library** | full source: SDK, model weights, DSP config | **Yes** — this is the one that admits a hand-written block |

The C++ library is then compiled locally into an **`.eim`** — an Edge Impulse
Model file. Despite the extension it is an ordinary ELF executable for the
target architecture that speaks the runner's IPC protocol over a Unix socket. It
is the same artefact the vision path already consumes, which is the point: the
acoustic model arrives in the format the rest of `device/mpu` already knows how
to talk to, so [`perception/acoustic_detector.py`](../../../../../device/mpu/perception/acoustic_detector.py)
needs no new transport.

## Building the `.eim`

```sh
# Clone with LF endings. A clone made by Windows git arrives with CRLF, and a
# Makefile with a trailing 
 puts a control character inside every variable
# value, which fails in ways that do not mention line endings.
git -c core.autocrlf=false -c core.eol=lf clone --depth 1     https://github.com/edgeimpulse/example-standalone-inferencing-linux
cd example-standalone-inferencing-linux

# Studio -> Deployment -> C++ library -> Build, then unpack over this tree
cp -r ~/Downloads/<project>-cpp/. .

# The Makefile compiles with -Iedge-impulse-sdk/tensorflow-lite, but the
# headers ship at the repo root and the export does not carry them.
cp -r tensorflow-lite edge-impulse-sdk/tensorflow-lite

# the piece Studio could not generate
cp <repo>/ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/panns_logmel.cpp      source/
cp <repo>/ml/acoustic/ei_blocks/dsp-panns-logmel/cpp/panns_logmel_core.hpp source/

# CXXSOURCES is an explicit wildcard list, not a glob over source/: each app
# variant adds only its own entry point, so the block must be named.
sed -i 's|^CCSOURCES =[[:space:]]*$|CXXSOURCES += source/panns_logmel.cpp

CCSOURCES =|' Makefile

APP_EIM=1 USE_FULL_TFLITE=1 TARGET_LINUX_AARCH64=1     CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ make -j"$(nproc)"
# -> build/model.eim
```

Three of those steps are easy to skip and none of them fail legibly:

- `USE_FULL_TFLITE=1` — without it the build targets TFLite-Micro with a
  statically sized arena, which this model's 21.9 MB of float32 weights will
  not fit.
- the `tensorflow-lite` copy — as noted above, the include path and the
  shipped location disagree.
- a real cross toolchain — upstream's README builds aarch64 with plain
  `clang`, which only works on an aarch64 host. `g++-aarch64-linux-gnu` is
  what actually cross-compiles.

`TARGET_LINUX_AARCH64=1` matters: the QRB2210 is aarch64, and the default
target is x86.

**Built and scored.** Both architectures link and run. Sizes are stripped,
with an unstripped copy kept alongside so a crash can still be symbolised:

| | stripped | unstripped |
|---|---|---|
| `model-aarch64.eim` | 27,422,976 B | 34,547,744 B |
| `model-x86_64.eim`  | 27,689,528 B | 34,780,816 B |

Most of that is the model: Studio converted the custom ONNX learn block to a
21.9 MB float32 `.tflite` and linked it in with INCBIN. Size is therefore a
second argument for the int8 question, alongside latency.

Both report identical metadata under `--print-info` — 8000 Hz, 80000 features,
four labels, project 1110036, impulse 19.

## Running it on the board

**This deployment uses no brick — but a brick path does exist, and an earlier
draft of this section described it wrongly.** That draft said to drop the
`.eim` into `/home/arduino/.arduino-bricks/ei-models/` so App Lab's Edge Impulse
brick would pick it up via an `EI_AUDIO_CLASSIFICATION_MODEL` environment
variable. It was written from the brick's published configuration rather than
from the board. Checking it against the board showed the *path* was invented —
`~/.arduino-bricks/ei-models/` does not exist; `~/.arduino-bricks/` contains one
empty `models/` directory dated to the factory image — and that neither our
application nor the production vision model goes anywhere near a brick. Our
`app.yaml` declares `bricks: []`.

What is true, and was checked against the board this time, is that
`arduino:audio_classification` is a real installed brick, that it advertises
support for "custom audio classification models trained on Edge Impulse
platform", and that a model can be registered with it. That route is described
under [Registering it as an App Lab brick](#registering-it-as-an-app-lab-brick)
below; it is not the route currently deployed.

What the board actually runs is the Edge Impulse Node CLI, which is a *wrapper*
around the `.eim` rather than a consumer of it:

```
edge-impulse-linux-runner --model-file <model>.eim --run-http-server <port>
```

The wrapper spawns the `.eim` as a child process, hands it a Unix socket under
`/dev/shm/`, speaks the socket protocol to it, and re-exposes the result as
plain HTTP. This matters for anyone reading the `.eim` in isolation: the binary
itself has **no** HTTP support — `--run-http-server` passed directly to it is
silently taken as a socket path, and it sits there waiting for a connection that
never comes. Grepping either the acoustic `.eim` or the production vision one
for `run-http-server` or `HTTP/1.1` returns nothing. The port belongs to the
Node process, not to the model.

`perception/acoustic_detector.py` and `services/config.py` already describe this
correctly; `ACOUSTIC_INFERENCE_URL` defaults to `http://127.0.0.1:1338`, and
vision occupies 1337 by the same arrangement.

### Verified drop-in

The locally cross-built `.eim` was copied to the board and run:

```
~/ArduinoApps/eletect-x/python/models/acoustic/acoustic-panns-20260930.eim
sha256 c36ab31fccea507209f37954ddd3395674a5e70b44ee96118e85d8d72d4835a7  (27,422,976 B, stripped)
```

The location follows the convention the vision models already use rather than
inventing a new one. Two details cost time and are worth recording. `node` is
not on `PATH` for a non-login shell, so the runner must be started with
`export PATH=$HOME/local/node-v20.19.2-linux-arm64/bin:$PATH` or it dies with
`env: 'node': No such file or directory`. And the runner is not on `PATH`
either; it lives at `$HOME/local/ei-cli/node_modules/.bin/`.

Started that way, it comes up clean and self-describing:

```
Starting HTTP server for Edge Impulse Experts / ETX-Test (v7) on port 1338
Parameters freq 8000Hz window length 10000ms. classes [ 'ambient', 'chainsaw', 'elephant_call', 'gunshot' ]
```

which confirms on the target what the host-side checks could only assert: the
8 kHz/10 s framing survived the round trip through Studio, and the four classes
arrived in the expected order. The binary is a native `ARM aarch64` ELF with
every shared library resolved, so nothing about the cross-build needs a
compatibility shim on this image.

### Registering it as an App Lab brick

The model **is** registered as an App Lab brick, and it serves inference from
inside one. Getting there took two things that are not obvious from the
outside, so both are recorded here: App Lab's own Edge Impulse import cannot
take this model at all, and the `.eim` has to be built against an older glibc
than the board itself runs.

What works is registering the locally built `.eim` as a custom model by hand;
`deployment/install/install-acoustic-brick.sh` does that. The model is
registered on the board now:

```
$ arduino-app-cli model list --format json | …
   etx-acoustic-panns-20260930 -> EleTect-X acoustic (PANNs Cnn10)
```

The last step — binding the brick in `app.yaml`, which is what moves it onto
port 1339 — is deliberately not done yet, because it restarts the app and the
app is the production deterrence stack. It also buys nothing until the USB
microphone is connected and `ACOUSTIC_ENABLED` flips. So the brick was instead
verified by running `ei-models-runner` with exactly the arguments
`brick_compose.yaml` passes it, on a spare port:

```
$ docker run -d -p 127.0.0.1:1340:1337 -v "$D:$D"       ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0       --model-file "$D/model.eim" --run-http-server 1337 --dont-print-predictions

$ curl -s http://127.0.0.1:1340/api/info
   "frequency": 8000, "input_features_count": 80000, "label_count": 4,
   "labels": ["ambient","chainsaw","elephant_call","gunshot"]
```

That is the brick's own image, model and command line, so what it proves
transfers; only the published port differs.

#### Why the import route is closed

The daemon on `127.0.0.1:8800` imports an Edge Impulse model with

```
PUT /v1/models/ei/projects/{projectID}     body: {"impulse_id": 19}
                                           header: x-api-key: <project key>
```

`InstallEIModel` then asks the platform for its deployment parameters, and for
board name `unoq` those are **hardcoded**:

```go
case "unoq":
    return EIDeploymentParams{ModelType: "float32", Engine: "tflite",
                              DeviceType: "runner-linux-aarch64"}, nil
```

So the precision is not the caller's to choose — there is no int8 path through
this route on an UNO Q, whatever Studio might offer. If no deployment of that
exact format exists, the importer asks Studio to build one. Project 1110036's
most recent deployment is `zip-linux` (the C++ library export this `.eim` was
cross-built from), which does not match, so the build fires. It fails:

```
Cannot build for "runner-linux-aarch64" as your project contains custom DSP
blocks. Use the C++ library export option and build locally.
```

Verified directly against Studio on 30 September 2026 — build job 54315745,
`modelType=float32`, `engine=tflite`, `type=runner-linux-aarch64` — rather than
inferred. This is the same refusal already seen for the `arduino-uno-q` target,
and the `cppType` addition to `parameters.json` does not lift it: `cppType`
lets the C++ export emit our feature function, but the hosted builders still
decline any project carrying an organisation DSP block. "Use the C++ library
export option and build locally" is precisely what this directory does.

#### What the brick actually requires

Much less than the importer. The models index scans the custom-models
directory for any subdirectory holding a `model.yaml` and loads the descriptor
beside the blob, so two files are enough:

```
/home/arduino/.arduino-bricks/models/<model-id>/
    model.eim      the blob
    model.yaml     the descriptor
```

That directory is `config.go`'s fallback when
`ARDUINO_APP_BRICKS__CUSTOM_MODEL_DIR` is unset, and it is the empty `models/`
already present on the board. The descriptor's schema is in
`custommodel/parser.go`; the one field worth flagging is that setting
`metadata.source: edgeimpulse` switches on a validator which requires
`ei-project-id`, `ei-impulse-id`, `ei-impulse-name` and
`ei-deployment-version` to be non-empty and `ei-model-type` to be exactly
`float32`.

An application then binds the model to the brick in `app.yaml`:

```yaml
bricks:
  - arduino:audio_classification:
      model: etx-acoustic-panns-20260930
```

This section has now been wrong twice in opposite directions, so the evidence
matters more than the snippet. The schema is defined in
`internal/orchestrator/app/parser.go` of `arduino/arduino-app-cli`:

```go
type Brick struct {
	ID        string            `yaml:"-"` // handled manually
	Model     string            `yaml:"model,omitempty"`
	Variables map[string]string `yaml:"variables,omitempty"`
	Devices   []string          `yaml:"devices,omitempty"`
}
```

`model` is a real manifest key. A previous revision of this file concluded it
was not, on the grounds that the ~25 stock example manifests under
`/var/lib/arduino-app-cli/examples/*/app.yaml` all write `bricks` as a flat
list of brick-ID strings:

```yaml
bricks:
  - arduino:web_ui
  - arduino:audio_classification
```

That observation is accurate; the inference drawn from it was not. `Brick` has
a custom `UnmarshalYAML` that accepts **both** shapes — a bare `ast.StringType`
node (the flat form above) and an `ast.MappingType` node whose single key is
the brick ID and whose value carries `model`, `variables` and `devices`. The
stock examples use the flat form only because none of them override a model.
The matching `MarshalYAML` always emits the mapping form, which is why App Lab
rewrites a manifest into mappings once the UI touches it.

The second piece of evidence was that the daemon's struct tags carry no
`yaml:"model"`. That came from grepping the stripped `/usr/bin/arduino-app-cli`
binary, where `yaml:"model,omitempty"` is stored as a distinct string from the
`yaml:"model"` that was searched for. The absence was an artefact of the grep,
not of the schema.

`description` is likewise a valid key (`yaml:"name"`, `yaml:"description"`,
`yaml:"ports"`, `yaml:"bricks"`, `yaml:"icon,omitempty"`), and per-brick
`devices` supersedes the app-level `required_devices`, which the same file
marks deprecated. No `version` key exists.

The brick's default model, used when `model` is omitted, comes from its own
declaration in `/var/lib/arduino-app-cli/assets/<ver>/bricks-list.yaml`:

```yaml
- id: arduino:audio_classification
  require_model: true
  model_name: glass-breaking      # <- the default, unless overridden
  variables:
    - name: EI_AUDIO_CLASSIFICATION_MODEL
      default_value: /models/ootb/ei/glass-breaking.eim
    - name: CUSTOM_MODEL_PATH
      default_value: /home/arduino/.arduino-bricks/ei-models
```

Two models now advertise `arduino:audio_classification` on this board — stock
`glass-breaking` and our `etx-acoustic-panns-20260930` — so the override is not
academic. Registration is already complete and visible to the daemon:
`arduino-app-cli brick details arduino:audio_classification --format json`
lists both under `compatible_models`, which is the same list the App Lab UI's
**Brick configuration** picker reads.

Selecting the model in that picker and writing `model:` into `app.yaml` are the
same operation — Arduino's own guidance is that the UI owns the file
("App Lab automatically saves these settings to your `app.yaml` file, and
passes them to the Brick as environment variables when the App runs", and
"Manual changes can cause syntax errors that prevent the editor from opening
your project"). For this app the manifest is hand-maintained anyway, because
App Lab's regeneration drops the golden-compose additions that the
self-healing watchdog re-applies (see HANDOVER.md).

Note also that `CUSTOM_MODEL_PATH`'s declared default is
`/home/arduino/.arduino-bricks/ei-models` — the path the earlier draft was
accused of inventing. It was not invented; it is the brick's documented
default. It simply does not exist on this board, and the daemon's models index
falls back to `/home/arduino/.arduino-bricks/models/`, which is where the model
actually lives and which the descriptor overrides `CUSTOM_MODEL_PATH` to point
at.

One further discrepancy worth carrying forward: `arduino-app-cli model list`
reports our model's `Runner` as **empty**, where every stock model reports
`brick`, even though our `model.yaml` sets `runner: "brick"` and every other
field in the same file parses correctly. `runner` is a real `yaml:` tag, so
this is not an unknown key being dropped silently. Whether an empty `Runner`
affects brick binding is untested — it did not prevent the model appearing in
the brick's `compatible_models`, but binding has never been exercised.

The brick itself is a Compose service, defined on the board at
`/var/lib/arduino-app-cli/assets/<ver>/compose/arduino/audio_classification/brick_compose.yaml`:

```yaml
services:
  ei-audio-classifier-runner:
    image: ${DOCKER_REGISTRY_BASE:-ghcr.io/arduino/}app-bricks/ei-models-runner:0.10.0
    ports:
      - ${BIND_ADDRESS:-127.0.0.1}:1339:1337
    volumes:
      - "${CUSTOM_MODEL_PATH:-/home/arduino/.arduino-bricks}:${CUSTOM_MODEL_PATH:-/home/arduino/.arduino-bricks}"
    command: ["--model-file", "${EI_AUDIO_CLASSIFICATION_MODEL:-/models/ootb/ei/glass-breaking.eim}",
              "--run-http-server", "1337", "--dont-print-predictions"]
    healthcheck:
      test: [ "CMD-SHELL", "wget -q --spider http://localhost:1337/api/info || exit 1" ]
```

Two details in there decide what the descriptor must say. The volume maps
`CUSTOM_MODEL_PATH` **to the same path inside the container**, so
`EI_AUDIO_CLASSIFICATION_MODEL` is a host absolute path, not a container one —
which is why the descriptor written by `install-acoustic-brick.sh` repeats the
host directory rather than rewriting it to something like `/models`. (The
built-in models do use container paths such as `/models/ootb/ei/…`; those come
from a different mount and are not a pattern to copy.) And the command is the
same `--run-http-server` wrapper described above, just supervised by Compose. Which
brick a model is offered to is derived from the *project category*, not the
learn block: `mapCategoryToBricks` sends `Keyword spotting` — this project's
category — to `arduino:audio_classification` and `arduino:keyword_spotting`.

#### What this would buy, and what it would cost

Two genuine gains. Compose supervises the runner, replacing the hand-rolled
systemd unit the vision runner needed. And the brick shares a Compose network
with the app, so the app can address the classifier by service name; the vision
runner had to be pushed host-side specifically because the App Lab container
cannot reach host `127.0.0.1:1337` over the bridge.

Two costs. The port moves to 1339 while `services/config.py`'s
`ACOUSTIC_INFERENCE_URL` still defaults to 1338. And the `.eim` has to be built
against the container's glibc rather than the host's, which is the next
section — the first build was not, and would not load.

#### Building it so the brick container can load it

The first `.eim` was cross-compiled on Ubuntu 24.04 with `aarch64-linux-gnu-g++`
(GCC 13, glibc 2.39). It runs on the board's host, which is Debian 13 with
glibc 2.41. It cannot run inside the brick, because
`ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0` is **Ubuntu 20.04** —
glibc 2.31, `libstdc++.so.6.0.28`. Checked directly rather than guessed:

```
$ docker run --rm -v <dir>:<dir> --entrypoint ldd \
      ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0 <dir>/model.eim
  .../model.eim: /lib/aarch64-linux-gnu/libc.so.6: version `GLIBC_2.38' not found
  .../model.eim: /lib/aarch64-linux-gnu/libc.so.6: version `GLIBC_2.34' not found
  .../model.eim: /lib/aarch64-linux-gnu/libc.so.6: version `GLIBC_2.32' not found
  .../model.eim: /lib/aarch64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.32' not found
  .../model.eim: /lib/aarch64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.30' not found
  .../model.eim: /lib/aarch64-linux-gnu/libstdc++.so.6: version `GLIBCXX_3.4.29' not found
```

The fix is to build against the runtime's own toolchain generation. Two
approaches were tried; only the second works, and the first is recorded
because it looks obviously right and is not.

**What does not work: a 20.04 sysroot with the 24.04 compiler.** Pointing
GCC 13 at an extracted `ubuntu-base-20.04` arm64 rootfs via `--sysroot` does
correctly resolve libc to 2.31, but the link then fails inside GCC's *own*
runtime:

```
libgcc_eh.a(unwind-dw2-fde-dip.o): undefined reference to `_dl_find_object'
libstdc++.a(ios_init.o):           undefined reference to `__libc_single_threaded'
```

`__libc_single_threaded` arrived in glibc 2.32 and `_dl_find_object` in 2.35.
A GCC packaged against glibc 2.39 compiles those uses into its own
`libstdc++`/`libgcc`, so no sysroot or `-static-libstdc++` can bring the
floor back down to 2.31. The compiler has to change, not just the headers.

Two smaller traps on the way there, worth knowing if you retry this:

- The Makefile puts `-lstdc++` in `LDFLAGS` explicitly, which defeats
  `-static-libstdc++` — the driver flag only governs the libstdc++ *it*
  adds. And `LDFLAGS` cannot be overridden on the `make` command line here,
  because the Makefile builds it with `+=`; a command-line value silently
  discards every TFLite library.
- `--sysroot` alone is not enough. The Debian cross toolchain also searches
  `/usr/aarch64-linux-gnu/lib`, which is the *host* release's aarch64 glibc,
  and that path is not sysroot-relative. Without explicit `-L` entries ahead
  of it, the link quietly picks up glibc 2.39 again and looks like it worked.

**What works: cross-compile from inside a Focal chroot.** Ubuntu 20.04's own
`crossbuild-essential-arm64` is GCC 9 built against glibc 2.31, so it cannot
emit a reference the brick container lacks. Running it in an amd64 chroot
keeps the build native — no qemu, same speed as before:

```bash
# one-time: a Focal amd64 root filesystem with the arm64 cross toolchain
curl -fsSLO https://cdimage.ubuntu.com/ubuntu-base/releases/20.04/release/\
ubuntu-base-20.04.5-base-amd64.tar.gz
mkdir -p focal/rootfs && tar xzf ubuntu-base-20.04.5-base-amd64.tar.gz -C focal/rootfs
cp /etc/resolv.conf focal/rootfs/etc/
mount -t proc proc focal/rootfs/proc
mount --rbind /sys  focal/rootfs/sys
mount --rbind /dev  focal/rootfs/dev
chroot focal/rootfs apt-get update
chroot focal/rootfs apt-get install -y --no-install-recommends \
    crossbuild-essential-arm64 make

# the build itself, unchanged apart from where it runs
mount --bind <source-tree> focal/rootfs/build
chroot focal/rootfs /bin/bash -c 'cd /build && make clean && \
    APP_EIM=1 USE_FULL_TFLITE=1 TARGET_LINUX_AARCH64=1 \
    CC=aarch64-linux-gnu-gcc CXX=aarch64-linux-gnu-g++ make -j"$(nproc)"'
```

Note this changes nothing about the model: same sources, same
`parameters.json`, same weights, same flags. Only the toolchain moves.

The claim that only the toolchain moved is checked, not asserted. The Focal
build is `ca7c895a…`, 35,918,456 bytes, against the 24.04 build's
`c36ab31f…`. Both were driven through `lat/onboard_latency.py` over the same
16 clips on the board, and they agree exactly:

| | 24.04 build, bare runner | Focal build, brick container |
|---|--:|--:|
| front end (ms) | 645.6 | 649.8 |
| classifier (ms) | 3490.7 | 3264.8 |
| total per 10 s window (ms) | 4136.3 | 3914.6 |
| real-time factor | 0.4136 | 0.3915 |
| correct, 16-clip subset | 15 | 15 |

Every prediction is the same, the one miss is the same clip
(`gunshot_100174`), and the largest difference in any confidence over the 16
clips is **0.000000** — the two binaries are numerically identical. That is
the expected result and worth stating plainly: the classifier is the same
prebuilt TFLite static library in both, and the recompiled parts are the DSP
front end, whose arithmetic did not change. Because the outputs are
bit-identical, the 92.56% argmax figure measured over the 605-clip test split
carries over to this artefact without re-running it.

The classifier column is 6% lower for the Focal build. That should be read as
*no regression*, not as a speed-up: the classifier stage is dominated by a
TFLite archive that is byte-for-byte the same in both builds, so the delta is
contention on a board that is simultaneously running the deterrence stack at
111% CPU, not code generation.

Verifying it in the place that matters:

```
$ docker run --rm -v $D:/m:ro --entrypoint ldd       ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0 /m/<old>.eim
  ... 7 lines of "version `GLIBC_2.xx' not found"

$ docker run --rm -v $D:/m:ro --entrypoint ldd       ghcr.io/arduino/app-bricks/ei-models-runner:0.10.0 /m/<new>.eim
  libstdc++.so.6 => /lib/aarch64-linux-gnu/libstdc++.so.6
  libc.so.6      => /lib/aarch64-linux-gnu/libc.so.6
  ...                                        (all resolved)
```

`install-acoustic-brick.sh` runs that check itself and refuses to register a
model that fails it, because it is the one property the host cannot observe:
the host is Debian 13 with glibc 2.41, so a too-new binary works there and
fails only once the brick starts it.

## Verifying the port

A DSP port that is only read is not a port, it is a rewrite with an optimistic
comment. The front end decides what the classifier sees, so an error here does
not crash — it costs accuracy, silently, with Studio's reported figures still
describing a model that is no longer the one running.

```sh
g++ -O2 -std=c++17 -Wall -Wextra parity_main.cpp -o parity_cpp
python parity_cpp.py
```

Sixteen probe signals, each chosen to break a log-mel implementation in one
specific way: tones at filterbank landmarks, tones just outside `fmin`/`fmax`,
broadband noise, a full-band chirp, impulses at the first and last sample (the
only probes that make the reflect padding observable), digital silence and
near-silence at the `amin` clamp, a full-scale square wave, and a length that is
not a multiple of the hop.

Two criteria, because the two comparisons are not the same kind of claim:

- **Against `../dsp.py`, absolute and unmasked.** This is what Studio ran while
  the model trained, so any disagreement is the port changing what the
  classifier sees. Worst observed: **1.53e-05 dB** across every cell of every
  probe, against a 1e-2 dB tolerance.
- **Against `torchlibrosa`, relative.** Inside the top 80 dB the port must be no
  further from it than `dsp.py` already is. It cannot be absolute, because
  torchlibrosa is the least accurate of the three: measured against a float64
  reference, librosa lands within 1e-5 dB, this port within 2e-5 dB, and
  torchlibrosa's own float32 conv1d STFT drifts as far as **6e-1 dB** on a pure
  tone. In the harness output the `cpp-vs-tl` and `py-vs-tl` columns are equal
  to four significant figures on every probe — the port inherits torchlibrosa's
  error exactly and adds none of its own.

`../parity_check.py` is the other half of the chain: it holds `dsp.py` against
torchlibrosa on real test clips, and additionally against Cnn10's embeddings.
Together the two say the C++ reproduces the front end PANNs was trained on.

### Verifying the resample path

`parity_cpp.py` starts from a signal already at 32 kHz, which is not the
deployed path. The 8 kHz leg needs its own harness because it cannot be held to
the same kind of claim:

```sh
python parity_resample.py
```

Two *different* filters cannot agree to 1e-2 dB everywhere, and a test that
demanded it would only get switched off. What they can be held to is **where**
the disagreement is allowed to land, so the harness splits the 64 mel bins
three ways and asserts only on the first:

| band | what it is | result |
| --- | --- | --- |
| support wholly below 3680 Hz | where an 8 kHz source's signal actually lives | **1.92e-01 dB** worst, against a 0.5 dB budget |
| straddling the transition | the two filters roll off differently by construction | 5.17e+00 dB, reported |
| support wholly above 4000 Hz | no content at all; one stopband versus another | 2.25e+00 dB, reported |

The split is by filter **support**, not centre frequency, and that distinction
is the whole test. A Slaney mel filter is a triangle spanning `edge[i]` to
`edge[i+2]`, so the bin centred at 3680 Hz still integrates out to 3891 Hz —
past the passband edge, into the region the two filters are designed to differ
in. Judged by centres, white noise showed a 2.03 dB "in-band" error that looked
like a real defect; judged by support the same measurement is 0.06 dB. Two
probes (tones at 3700 and 3900 Hz) are reported but not asserted for the same
reason: all their energy sits at or above the passband edge, so asserting on
them would be asserting that two different filters are the same filter.

### What the dB budget does not prove

It does not prove the remaining disagreement is harmless. That claim needs the
classifier, so it was measured against it: all 605 test clips scored through
`cnn10_10s_fp32.onnx` twice, once resampled by librosa's soxr_hq exactly as
`harness/embed.py` does it, once by this port.

| resampler | accuracy | argmax flips | max Δprob | mean Δprob |
| --- | --- | --- | --- | --- |
| librosa soxr_hq (reference) | 91.90% (556/605) | — | — | — |
| port at `pass_fraction` 0.931 | 91.74% (555/605) | 1 | 0.169 | 0.0034 |
| **port at 0.920 (shipping)** | **91.90% (556/605)** | **0** | **0.063** | **0.0012** |

The reference leg reproducing the published 91.90% exactly is what makes the
other two rows worth reading — it says the experiment is measuring the
resampler and not itself. The shipping filter changes **no prediction on any
clip in the test set**.

Two supporting checks, both green: the C++ filter coefficients match the numpy
design to **1.9e-15** with symmetry error exactly 0.0, and the hand-rolled
`BesselI0` matches `np.i0` to machine precision.

One residual is known and not chased. The two resamplers differ by 8.6e-03 in
the first and last ~40 output samples, which is FIR edge handling — soxr's
padding policy is not implicit zero-padding. That is 40 samples out of 128000,
and the 605-clip test says it costs nothing. Recording it here is cheaper than
re-deriving it the next time someone diffs the two waveforms.

### Compiling the block itself

`parity_cpp` exercises `panns_logmel_core.hpp`. The file that actually ships is
`panns_logmel.cpp`, and it cannot be compiled without the inferencing SDK -
which only arrives with a Studio export.

```sh
./syntax_check.sh                 # or: ./syntax_check.sh clang++
```

builds a minimal include tree from `stubs/` plus the two real headers that
define the contract (`dsp/numpy_types.h`, `dsp/returntypes.hpp`, downloaded
rather than vendored, since they are copyright Edge Impulse) and compiles the
block against it under `-std=c++14 -Wall -Wextra`, matching what
`example-standalone-inferencing-linux` builds with.

This is not ceremony. The first version of this port compiled its own core
cleanly and would still have failed at an integrator's build: the `EIDSP_*`
status enumerators live in namespace `ei`, and much of Edge Impulse's own DSP
source opens that namespace wholesale, so unqualified `EIDSP_OK` reads as
though it were global. The check caught it; review had not.

It passes under both forms of `signal_t` - the `std::function` default and the
raw function pointer selected by `EIDSP_SIGNAL_C_FN_POINTER=1` - so the block
does not depend on which the host project chose.

The script normalises its scratch path to drive-letter form before using it.
That is not incidental tidiness: on Windows, MSYS mounts `/tmp` at the user's
AppData temp directory while busybox-w32 - which lands on `PATH` ahead of MSYS
the moment a w64devkit compiler does - reads `/tmp` literally as `C:	mp`. The
stubs were being copied to one of those and the compiler pointed at the other,
which surfaced as `ei_model_types.h: No such file or directory` and reads
exactly like a missing SDK. There is now an explicit check for the copy having
landed, so the next occurrence names itself.

The core additionally compiles clean at `-std=c++11`, `c++14` and `c++17` with
`-Wall -Wextra -Wpedantic`.

### Scoring the built `.eim`

Everything above stops at the features. It says nothing about whether Studio's
ONNX-to-TFLite conversion of the learn block survived, nor whether the runner
wires the two together the way the impulse describes. Running real clips
through the finished `.eim` covers all three at once, and the number it
produces is directly comparable to the accuracy Studio reports.

`harness/eim_testset.py` drives the runner over the frozen test split — clips
read at their native 8 kHz and handed over as int16 counts, which is what Edge
Impulse serves for audio and what the block's rescale heuristic expects. The
4x upsample to the PANNs filterbank happens inside the block, on the deployed
path, exactly as it will in the field.

The split used is the same one the offline harness uses, and it is also
exactly the partition uploaded to Edge Impulse as `testing` — checked against
`ei_upload_ledger.json` rather than assumed: 605 of 605 harness-test clips are
EI-test, and no harness-test clip is in EI's training partition. Without that
check the comparison below would be worthless, because the two sides would be
reporting on different data.

Results are in [`results_eim_impulse19.json`](../../../harness/results_eim_impulse19.json).

| | accuracy |
|---|---|
| argmax, no threshold | **92.56%** (560/605) |
| at EI's default 0.6 confidence threshold | **87.93%** (532/605) |
| Studio's reported figure for impulse 19 | 87.77% (531/605) |

The middle row is the one that matters. Edge Impulse's model-testing page
counts a below-threshold window as wrong rather than abstaining, so its
headline number is thresholded; this script takes plain argmax. Scored the way
Studio scores, the locally built `.eim` lands one clip away from Studio's own
figure — which is as close as two different runtimes over 605 clips are going
to get, and it validates the whole chain: the hand-written DSP block, the
resampler, the converted learn block and the runner.

It also settles a comparison that had been recorded as a discrepancy. The
91.9% on record for `cnn10_10s_fp32.onnx` is an argmax number, so setting it
against Studio's thresholded 87.77% was never like-for-like. Compared
properly, over the identical 605 clips at argmax:

| | overall | ambient | chainsaw | elephant_call | gunshot |
|---|---|---|---|---|---|
| `cnn10_10s_fp32.onnx` | 91.90% | 0.911 | 0.912 | 0.914 | 0.930 |
| deployed `.eim` | **92.56%** | 0.928 | 0.912 | 0.931 | 0.926 |

(per-class figures are recall). The deployed impulse is ahead overall and on
two of four classes, level on chainsaw, and 0.4 points — one clip — behind on
gunshot recall. There is no accuracy cost to deploying through Edge Impulse
here, so impulse 19 stands.

#### The same answers on ARM

The aarch64 binary cannot run on an x86 host, so it was scored under
`qemu-aarch64-static` over a stratified subset. The point is not accuracy — it
is that a hand-written DSP kernel gives the same answers on ARM as on x86.
Differences in float contraction, vectorisation or libm between the two
toolchains would show up here and nowhere else available while the board is
out of scope.

Over 8 clips: **zero argmax disagreements**, and the largest difference in any
class score was **3.6e-07**, which is float32 rounding rather than divergence.
The one misclassification in that subset is the same clip on both
architectures, so it is the model's error, not the port's.

Timings from the qemu run are emulation artefacts and are not recorded. The
x86 host split — 278 ms front end, 465 ms classifier per 10 s window — is
measured but is not the board either; it is useful only as evidence that the
front end is a real fraction of the total, which is the part Studio's 4,134 ms
leaves out.

## Notes on the implementation

**Double precision inside the FFT.** Measured, not fastidious. With float32
twiddles the per-factor rounding compounds across all ten radix-2 stages and the
resulting noise floor lands on the spectral leakage floor of a pure tone; bins
100 dB down then disagreed with librosa by ~0.1 dB, because the computation was
reporting its own noise. That was outside the band PANNs normalisation keeps, so
it could not have changed a prediction — but a parity test that has to be told
which cells to ignore is a weaker test. In double the same probes agree to
~1e-5 dB unmasked. The cost is invisible: the whole DSP stage is a few million
flops against a classifier block Studio estimates at **4,134 ms** on this
silicon.

**A full complex FFT on real input.** Twice the necessary arithmetic, for the
same reason — the packed real-FFT split is the classic place to introduce a
silent, spectrum-mangling bug in exactly this kind of port.

**Resampling is part of the front end, not an option.** This is the part of the
port that is easiest to get wrong by leaving out.

The impulse declares `EI_CLASSIFIER_FREQUENCY 8000`, because the corpus is
8 kHz throughout. PANNs' filterbank is defined at 32 kHz. So every window the
model has ever seen — in training, in Studio's test set, and on the board — went
through a 4× upsample first. In Python that happens twice over: `../dsp.py:147`
calls `librosa.resample`, and before that `harness/embed.py` loads every clip
with `librosa.load(..., sr=32000)`, which resamples on the way in. An earlier
version of this port refused any rate other than 32 kHz, which would have been
correct only if the deployed path never hit it. It hits it on every window.

The reference is therefore specific, not generic: `librosa.resample`'s default
`res_type` is **`soxr_hq`**, and that is the filter the model was trained
behind. Reproducing it by embedding soxr's coefficients is not available here —
soxr is LGPL and this tree is MIT — so the port carries an own-work polyphase
Kaiser windowed-sinc designed against soxr_hq's *measured* response rather than
its documentation. Measured at L=4: flat to within 0.1 dB up to 3724 Hz,
−24.4 dB at 3900 Hz, −141.7 dB at 4000 Hz, stopband below −131 dB. soxr_hq is
linear-phase and shift-invariant at this ratio (measured shift error 6e-08,
kernel sum exactly 4.0), so a fixed FIR is the right shape of answer.

One parameter had to be fitted rather than quoted. Placing the cutoff at
soxr's own −0.1 dB point (0.931 of input Nyquist) rolls off later than soxr
actually does; sweeping it against the measured response puts the best fit at
**0.920**, which drops the RMS transition-band error from 4.15 dB to 1.45 dB
*and* needs fewer taps (921 rather than 1067). The constant is
`kPassbandFraction` and the comment beside it records this.

Rates that are not an integer divisor of 32 kHz are still refused. `../dsp.py`
would resample anything at all through librosa, but the only rates this impulse
can be fed are 8 kHz and 16 kHz, and a general rational resampler written to
cover rates nobody uses would be untested code on the one path that decides
what the classifier sees.

Capture is pinned to 8 kHz upstream in
[`perception/microphone.py`](../../../../../device/mpu/perception/microphone.py),
using ALSA's `plughw:` so the kernel converts from whatever the USB codec
advertises. Note what that means: feeding 32 kHz would not *skip* the upsample,
it would push an already-4×-fast signal through it and land every frequency in
the wrong mel bin — which a PANNs backbone reports as confident wrong labels,
not as an error.

One consequence is worth stating in the write-up rather than hiding: an 8 kHz
source has nothing above 4 kHz, so 21–22 of the 64 mel bins carry only the
resampler's stopband, around 107 dB below peak. PANNs spends the top ~40% of
its filterbank on an empty band, which is a sufficient explanation for chainsaw
being the weak class. Dropping `fmax` to 4000 is **not** the fix — the
pretrained backbone expects the 50–14000 Hz layout, and moving it invalidates
the transfer.

**`peak_crop` is intentionally unread.** In `../dsp.py` it is applied as
`peak_window(y, sr, len(y)/sr)`, whose crop length always equals the input
length, so the function returns the signal unchanged — the parameter is a no-op
on the Studio path it was meant to affect. Reproducing a no-op would add an
untestable branch. If peak cropping ever becomes real in the Python, it has to
be added here in the same commit.

## Open items

Per-window cost is now measured on the QRB2210 rather than estimated, which
closes the largest open item here and corrects the estimate that stood in for
it. Sixteen clips through the deployed runner, two runs:

| | run 1 | run 2 |
| --- | --: | --: |
| front end (DSP) | 662 ms | 646 ms |
| classifier | 3,647 ms | 3,491 ms |
| **total per 10 s window** | **4,310 ms** | **4,136 ms** |
| wall clock incl. HTTP + JSON | 4,511 ms | 4,274 ms |

Both runs were taken with the production stack live — the application at ~111%
CPU and the vision runner at ~69%, load average 3.33 across 4 cores — so these
are the contended numbers the field would see, not a quiescent best case. The
real-time factor is **0.41–0.43**: roughly 4.2 s of compute per 10 s of audio.

Two corrections fall out of this.

Studio's **4,134 ms** was described here as excluding the front end and
therefore being an underestimate. It is not an underestimate. It lands *inside*
the measured range of the **total** (4,136–4,310 ms), and well above the
classifier taken alone (3,491–3,647 ms). Why an estimate that cannot profile
the custom block should match the figure including that block is unexplained,
and coincidence has not been ruled out — two runs are not enough to call it
predictive. It should still not be quoted as an authority, but the specific
claim that it omits the front end is now contradicted by measurement.

The front end is also **not** the dominant cost. It is 15–16% of the total; the
classifier is the other 84%. An int8 variant therefore acts on the part that
actually dominates, which strengthens rather than weakens the case for it — see
[ADR 0030](../../../../../docs/decisions/0030-acoustic-int8-reopened-against-the-panns-model.md),
which supersedes 0026. Studio offered no int8 option for this impulse, likely
because the learn block is custom and ships its own ONNX; that still needs
confirming rather than assuming.

Remaining:

- Whether int8 is faster *on this target* is still unmeasured. ADR 0030 removes
  the reason to expect it to be slower but does not establish that it is faster.
- A quiescent measurement, with the application and vision runner stopped, would
  separate model cost from contention. It needs the running soak paused, so it
  is a scheduling decision rather than a technical one.

See [ADR 0028](../../../../../docs/decisions/0028-acoustic-capture-moves-to-the-mpu-usb-microphone.md)
for why acoustic capture sits on the MPU at all.
