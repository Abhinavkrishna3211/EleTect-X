# Edge Impulse Linux inference on the Arduino UNO Q (QRB2210)

Research notes for the EleTect X on-device vision detector. Focus: is GPU/NPU/DSP
acceleration real on this board, and can we lock camera exposure at night.

Date of research: 2026-09-02. All external claims linked to source. Anything not
confirmed against a primary source is in "Unverified / open" at the bottom.

---

## Top-line summary

**GPU / NPU / DSP acceleration: effectively NO on the UNO Q today.**

- The QRB2210 (and its sibling QCS2290) has **no NPU / Hexagon Tensor Processor**.
  Qualcomm's own IoT application-processor selector guide lists NPU as **N/A** for
  this part. It has an Adreno 702 GPU and an always-on Hexagon DSP intended for
  low-power audio / sensor fusion, not a tensor-accelerator path exposed to ML
  runtimes. So there is no "route int8 ops to the NPU" story here at all.
- Edge Impulse *does* publish a "Linux Arduino UNO Q (GPU)" / `runner-linux-aarch64-gpu`
  deployment target, and it compiles in their cloud, but it depends on
  `libtensorflowlite_gpu_delegate.so`, which is not shipped in the Arduino Debian
  image and not in any apt repo (confirmed on-board by us, and matched by forum
  reports). The TFLite GPU delegate on Linux needs a working OpenCL (or GLES)
  stack on the Adreno; the UNO Q image ships Mesa "Turnip" (Vulkan-only) + freedreno
  and **no Qualcomm proprietary OpenCL/GLES userland**, so the delegate cannot
  initialise even if the `.so` were present. Multiple community attempts
  (TFLite GPU delegate, `onnxruntime-qnn`) fail for exactly this reason, with no
  official Arduino / Edge Impulse fix as of mid-2026.
- The Qualcomm QNN path (`USE_QUALCOMM_QNN=1`, Studio target "Linux (AARCH64 with
  Qualcomm QNN)") is real, but it targets the **Hexagon HTP/Tensor** on
  higher-tier Dragonwing parts (QRB6490 / Rubik Pi 3, QRB5165 / RB5). The UNO Q's
  QRB2210 has no HTP, and the QNN userland libraries are not installed, so this
  target does not apply.
- **CPU is the ceiling.** Inference runs on the 4x Arm Cortex-A53 with NEON +
  XNNPACK, int8, EON-compiled. Our measured ~138 ms/frame (~5.7 FPS) is in the
  expected range for a small model on this class of core. Edge Impulse publishes
  no official UNO Q FPS figure. Levers below are all software/model-side.

**Camera exposure: YES, we can lock it — but the clean, supported way for our
project is to own the camera in our app and feed frames to the runner.**

- The `edge-impulse-linux` CLI / runner opens the camera through **GStreamer**
  (`gst-launch-1.0`), default pipeline roughly
  `v4l2src device=/dev/video0 ! video/x-raw,... ! videoconvert ! jpegenc`. The
  whole pipeline is overridable with `--gst-launch-args`.
- If the camera enumerates on the **`v4l2src`** path you can set
  `v4l2src extra-controls="c,auto_exposure=1,exposure_time_absolute=256,gain=<n>"`
  inside `--gst-launch-args` (V4L2 UVC: `auto_exposure=1` = manual, `=3` =
  aperture-priority auto). Equivalently, run
  `v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=1,exposure_time_absolute=256`
  before/while the runner is live.
- On the UNO Q, USB webcams have been seen coming up under **`libcamerasrc`**
  instead (Edge Impulse staff gave a `libcamerasrc` workaround for a Logitech C270).
  `libcamerasrc` does **not** reliably expose exposure/gain as GStreamer element
  properties, so the v4l2 trick may not reach the sensor on that path.
- The robust answer, and the one that matches the side V4L2 harness we already
  have: **the application owns the camera** (V4L2 directly, AGC off, exposure
  pinned ~256), and passes frames to the model via the Python SDK
  (`ImageImpulseRunner.get_features_from_image()` + `.classify()`), the C++ SDK
  `APP_CAMERA`/custom path, or the `edgeimpulsevideoinfer` GStreamer element in a
  pipeline we build. This bypasses the runner's camera code entirely and is fully
  supported.

---

## Q1. Is GPU / NPU / DSP acceleration supported by the EI Linux runner on the UNO Q?

### QRB2210 silicon reality

- Qualcomm's *Application Processors for IoT Selector Guide* lists QRB2210 /
  QCS2290 as 4x Cortex-A53 @ up to 2.0 GHz + Adreno 702, with **NPU = N/A** — no
  dedicated neural accelerator on this part.
  <https://www.qualcomm.com/content/dam/qcomm-martech/dm-assets/documents/Qualcomm-Application-Processors-for-IoT-Selector-Guide.PDF>
- QRB2210 product brief / overview: quad Kryo (Cortex-A53) CPU, Adreno 702 GPU
  (OpenGL ES 3.1, OpenCL 2.0, Vulkan 1.1 *as a silicon capability*), 2x ISP, and
  an **always-on Hexagon DSP for low-power sensor fusion / voice / audio** — i.e.
  not positioned as an ML tensor engine.
  <https://docs.qualcomm.com/doc/87-61720-1/87-61720-1_REV_D_Qualcomm_Dragonwing_QRB2210_Processor_Product_Brief.pdf>
  <https://www.qualcomm.com/internet-of-things/products/q2-series/qrb2210>
- Qualcomm's Hexagon NPU (tensor cores, mixed precision) exists only on higher-end
  Snapdragon / Dragonwing parts, not the entry Q2 series.
  <https://chipsandcheese.com/p/qualcomms-hexagon-dsp-and-now-npu>

### The EI "Linux Arduino UNO Q (GPU)" target

- Edge Impulse's Arduino App Lab docs list the deployment options for the board as
  "Linux aarch64 **or Linux Arduino UNO Q (GPU)**", and models are `.eim` files
  copied to `/home/arduino/.arduino-bricks/ei-models/`.
  <https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab>
- The UNO Q board page claims deployment "will automatically compile your model
  with full hardware acceleration" — this is marketing language; in practice the
  accelerated build is the GPU-delegate `.eim`, which is what fails on the board.
  <https://docs.edgeimpulse.com/hardware/boards/arduino-uno-q>
- The GPU `.eim` needs `libtensorflowlite_gpu_delegate.so`. That library is a
  Bazel build product of upstream TensorFlow
  (`tensorflow/lite/delegates/gpu:libtensorflowlite_gpu_delegate.so`) and, on
  Linux, wants OpenCL 1.2+ (with a GLES fallback) at runtime; if `libOpenCL.so`
  is not resolvable the delegate errors or silently falls back.
  <https://github.com/tensorflow/tensorflow/issues/54269>
  <https://github.com/tensorflow/tensorflow/issues/58435>
- The UNO Q Debian image's Adreno support is the **Mesa open stack (Turnip =
  Vulkan, freedreno)**; there is **no Qualcomm proprietary OpenCL/GLES driver**.
  Community confirmation:
  - `onnxruntime-qnn` / GPU inference attempt → `QNN_BACKEND_ERROR_CANNOT_INITIALIZE`;
    poster's conclusion: "the UNO Q doesn't have the proprietary Qualcomm OpenCL
    drivers for the Adreno 702 GPU" (deneb23, 22 Jun 2026).
    <https://forum.arduino.cc/t/ai-inference-on-uno-q-adreno-702-gpu-without-app-lab/1449276>
  - FastRPC kernel + ADSP firmware boot, Vulkan/OpenCL via Turnip work, **but "no
    FastRPC/QNN userland libraries installed"**; five open questions to Arduino/EI
    with no staff answer (speccy, 8 Jun 2026).
    <https://forum.arduino.cc/t/status-of-qualcomm-qnn-tflite-delegate-edge-impulse-qnn-acceleration/1447565>
- So our on-board apt/filesystem search result is correct and expected: the GPU
  delegate is genuinely not available, and there is no supported way to make the
  cloud-built GPU `.eim` run.

### QNN / Hexagon path

- Edge Impulse QNN acceleration (blog + Android tutorial) routes int8 TFLite ops
  to the **Hexagon HTP/DSP via the QNN TFLite Delegate**, requires INT8 models,
  and needs `libQnnTFLiteDelegate.so`, `libQnnHtp.so`, `libQnnHtpV**.so`,
  `libQnnHtpV**Skel.so`, `libQnnSystem.so`, `libQnnIr.so`.
  <https://docs.edgeimpulse.com/tutorials/topics/android/qnn-acceleration>
  <https://www.edgeimpulse.com/blog/unlocking-hardware-acceleration-for-android-with-qualcomm-qnn/>
- Supported hardware named by EI: Snapdragon 8/7+/6-gen mobile, **QRB6490 (Rubik
  Pi 3), QRB5165 (RB5)**, "Dragonwing platforms". QRB2210 / QCS2290 are **not**
  listed, consistent with them having no HTP.
- Studio has a "Linux (AARCH64 with Qualcomm QNN)" deployment and a Qualcomm
  setup script (`setup-edge-impulse-qc-linux.sh`), but that is for the
  HTP-equipped Dragonwing boards, not the UNO Q.
  <https://docs.qualcomm.com/doc/80-80022-15B/topic/edge-impulse.html>
- C++ SDK exposes `USE_QUALCOMM_QNN=1` with `TARGET_LINUX_AARCH64=1`; irrelevant
  here because there is no HTP and no QNN userland on the board.
  <https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/cpp>

### Other delegate ideas we considered

- **mesa-teflon-delegate**: Mesa's TFLite delegate is aimed at VeriSilicon and a
  few other embedded NPUs, not Adreno; it is not a drop-in for the EI runner and
  would not accelerate on QRB2210.
- **ArmNN GPU backend**: targets Mali GPUs via its own CL backend, not Adreno /
  the EI runner's TFLite interpreter — architecturally not a drop-in, matches our
  earlier assessment.
- The newer **Arduino VENTUNO Q (Qualcomm Dragonwing IQ-8275)** *does* have a real
  NPU; that is the board EI's accelerated story is really written for. Not our
  hardware.
  <https://www.edgeimpulse.com/blog/announcing-arduino-app-lab-full-integration-and-ventuno-q/>

**Answer: No supported GPU/NPU/DSP acceleration on the UNO Q via the EI Linux
runner today. CPU (Cortex-A53 + NEON + XNNPACK, int8, EON) is the ceiling.**

---

## Q2. Flex delegates — what they are, and do they help / run on aarch64?

- Definition (EI docs, verbatim): "On Linux platforms without a GPU or neural
  accelerator your model is run using LiteRT (previously Tensorflow Lite). Not
  every model can be represented using native LiteRT operators. For these models,
  'Flex' ops are injected into the model."
  <https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/flex-delegates>
- **They add operator coverage, not speed.** Flex ops run the missing operations
  through the full TensorFlow kernel set **on CPU**. They do not touch GPU/NPU and
  will not reduce our inference time; if anything the flex-routed ops are slower
  than native LiteRT kernels.
- **aarch64 Linux: yes, supported.** EI ships `libtensorflowlite_flex_2.16.1.so`
  builds for macOS x86, Linux armv7, **Linux aarch64 (e.g. Jetson Nano)**, and
  Linux x86_64. Install: drop the `.so` in `/usr/lib` or `/usr/local/lib`. C++
  builds need `LINK_TFLITE_FLEX_LIBRARY=1`; Python / Node / Go `.eim` files
  already have it linked in.
- **Relevance to us:** only if a Studio deployment warns that our impulse needs
  flex ops (usually from an exotic layer). A standard FOMO / MobileNet vision
  model compiles to native LiteRT + EON and needs no flex delegate. Flex is not a
  performance lever and not a route to the GPU.

---

## Q3. How does the EI Linux runner capture camera frames, and can exposure / gain / AGC be controlled?

### Capture path

- **CLI (`edge-impulse-linux`, `edge-impulse-linux-runner`): GStreamer.** Frames
  come from a `gst-launch-1.0` pipeline that must emit JPEG, default similar to
  `v4l2src device=/dev/video0 ! video/x-raw,width=640,height=480 ! videoconvert ! jpegenc`.
  Relevant flags:
  `--gst-launch-args "<pipeline>"` (override the whole pipeline),
  `--camera <name|addr>`, `--width <px>`, `--height <px>`.
  <https://docs.edgeimpulse.com/tools/clis/edge-impulse-linux-cli>
- On the UNO Q, USB webcams have been observed enumerating under the **libcamera**
  GStreamer plugin, not `v4l2src`. EI staff (mateusz, Oct 2025) workaround:
  `edge-impulse-linux --gst-launch-args "libcamerasrc camera-name='...' ! video/x-raw,width=640,height=480 ! videoconvert ! jpegenc"`,
  plus `sudo usermod -a -G kvm <user>` to clear a DmaBufAllocator error. Find the
  camera path with `gst-device-monitor-1.0`.
  <https://forum.edgeimpulse.com/t/arduino-uno-q-issues-with-running-edge-impulse-linux/16762/20>
- **Python SDK (`ImageImpulseRunner`): OpenCV.** Opens the camera with
  `cv2.VideoCapture(videoDeviceId)` (default 0). No exposure/gain API on that
  object as used.
  <https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/python>
  <https://github.com/edgeimpulse/linux-sdk-python>
- **C++ SDK:** `APP_CAMERA=1` builds a realtime image classifier; `APP_EIM=1`
  builds the `.eim` that the higher-level SDKs drive over a Unix socket. The `.eim`
  itself is "signal processing + ML code compiled with NEON optimisations + a
  simple IPC layer over a Unix socket" — it does not own the camera.
  <https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/cpp>
  <https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux>

### Controlling exposure / gain / AGC

There is **no dedicated runner flag or env var** for exposure/gain/AGC. Options,
best first for our use case:

1. **App owns the camera, feeds frames to the model (supported, matches our
   harness).**
   - Python: `runner.get_features_from_image(img)` then `runner.classify(features)`
     — `img` is any RGB numpy array. The camera is never opened by the SDK, so we
     open `/dev/video0` ourselves with V4L2, set `V4L2_CID_EXPOSURE_AUTO = manual`,
     `V4L2_CID_EXPOSURE_ABSOLUTE ~ 256`, gain fixed, then hand frames in.
     <https://github.com/edgeimpulse/linux-sdk-python>
   - GStreamer plugin `edgeimpulsevideoinfer` (repo `edgeimpulse/gst-plugins-edgeimpulse`,
     aarch64 supported): build the pipeline ourselves, e.g.
     `v4l2src extra-controls="c,auto_exposure=1,exposure_time_absolute=256" ! videoconvert ! video/x-raw,format=RGB ! edgeimpulsevideoinfer ! ...`.
     <https://github.com/edgeimpulse/gst-plugins-edgeimpulse>
2. **CLI runner + `--gst-launch-args` with a v4l2 pipeline** (works only if the
   camera is reachable via `v4l2src`, not libcamerasrc):
   `edge-impulse-linux-runner --gst-launch-args "v4l2src device=/dev/video0 extra-controls=\"c,auto_exposure=1,exposure_time_absolute=256,gain=32\" ! video/x-raw,width=640,height=480 ! videoconvert ! jpegenc"`.
   `auto_exposure=1` = manual, `=3` = aperture-priority auto (V4L2 UVC semantics).
   <https://discourse.gstreamer.org/t/how-to-control-exposure-and-gain-using-gstreamer/5596>
   <https://thiblahute.github.io/GStreamer-doc/video4linux2-1.0/v4l2src.html>
3. **Set controls out of band** with `v4l2-ctl` before/while the runner streams:
   `v4l2-ctl -d /dev/video0 --set-ctrl=auto_exposure=1,exposure_time_absolute=256,gain=32`.
   Fragile: some UVC cameras reset controls when the stream (re)starts, and if the
   runner drives the sensor through libcamera these V4L2 writes may be ignored.
4. **If the camera comes up under `libcamerasrc`:** libcamera's manual-exposure
   controls are `AeEnable=false` / `ExposureTimeMode` + `ExposureTime` +
   `AnalogueGain`, but `libcamerasrc` "doesn't expose exposure and gain properties
   through standard GStreamer mechanisms like v4l2src does" — check
   `gst-inspect-1.0 libcamerasrc` on the actual board image. Prefer forcing the
   camera onto `/dev/videoN` + `v4l2src`, or option 1.
   <https://discourse.gstreamer.org/t/how-to-control-exposure-and-gain-using-gstreamer/5596>
   <https://libcamera.org/api-html/namespacelibcamera_1_1controls.html>

**Conclusion:** feeding our own AGC-off frames to the runner (option 1) is the
supported, portable way to get a locked ~256 exposure at night. The CLI
`--gst-launch-args` v4l2 route can also work but depends on how the UNO Q image
enumerates the camera and on the camera honoring UVC manual-exposure.

---

## Q4. EON Compiler options and other documented ways to cut latency without retraining

### EON Compiler

- Turns the model into "highly efficient and hardware-optimized C++ source code";
  vs TFLite Micro / interpreter it gives **25-65% less RAM, 10-35% less flash,
  same accuracy, faster inference**. This is the default and already active for
  our deploy.
  <https://docs.edgeimpulse.com/studio/projects/deployment/eon-compiler>
- **EON Compiler (RAM optimized)** (Enterprise only): recomputes intermediates on
  demand → lower RAM but **"a slightly higher latency cost"**. Do **not** use it
  when chasing speed.
- Limits: unsupported operators and complex residual layers reduce how much EON
  can optimize.

### Latency levers that don't need a new dataset

- **int8 quantized variant.** Use the int8 `.eim` (`--quantized` on the runner,
  or select the int8 model variant). int8 + XNNPACK on Cortex-A53 is markedly
  faster than float32. EI's own benchmarks are "all 8-bit quantized, compiled with
  EON".
  <https://docs.edgeimpulse.com/knowledge/metrics/inference-performance>
  <https://docs.edgeimpulse.com/tools/clis/edge-impulse-linux-cli>
- **Smaller input resolution.** Inference time scales roughly with pixel count;
  EI's reference numbers show a 96x96 model at 140 ms vs a 32x32 model at 13 ms on
  the same core. Dropping e.g. 160→120 or 96→64 is the biggest single knob.
  <https://docs.edgeimpulse.com/knowledge/metrics/inference-performance>
- **Grayscale instead of RGB.** ~3x fewer input channels / first-layer MACs; EI's
  reference set explicitly contrasts "96x96 color" vs "32x32 grayscale".
- **FOMO for object detection.** FOMO is "~30x faster than MobileNet SSD, runs in
  <200K RAM", ~30 FPS on a Cortex-M7 Nicla Vision. Switching the object-detection
  learn block to FOMO reuses the **same labelled data** (retrains only the head,
  no new collection). This is the highest-leverage change if we are on
  MobileNet-SSD / YOLO now.
  <https://www.edgeimpulse.com/blog/announcing-fomo-faster-objects-more-objects/>
  <https://docs.edgeimpulse.com/studio/projects/learning-blocks/blocks/object-detection/fomo>
- **Lighter backbone alpha.** MobileNetV2 alpha 0.35 / 0.1 vs 1.0 — fewer MACs,
  retrain from same data.
  <https://docs.edgeimpulse.com/knowledge/guides/increasing-model-performance>
- **Multi-threaded CPU inference.** The board has 4x A53; `USE_FULL_TFLITE`
  builds enable XNNPACK multi-threading. Confirm the runner/`.eim` is using more
  than one thread (check `--profiling`).
  <https://docs.edgeimpulse.com/tools/libraries/sdks/inference/linux/cpp>
- **Match capture resolution to model input.** EI staff (mateusz): pick a camera
  resolution "the same or higher than the model input resolution" and no larger —
  excess resolution just wastes resize time.
  <https://forum.edgeimpulse.com/t/arduino-uno-q-issues-with-running-edge-impulse-linux/16762/20>
- **Resize mode.** `--force-resize-mode {squash,fit-shortest,fit-longest}` to
  avoid an extra crop/pad pass.
  <https://docs.edgeimpulse.com/tools/clis/edge-impulse-linux-cli>
- **Inspect available engines/variants:** `edge-impulse-linux-runner --list-targets`,
  then `--force-target` / `--force-engine` / `--force-variant`. On the UNO Q the
  only viable engine is CPU TFLite; this is mainly to *avoid* the broken GPU
  target being auto-selected.
- **DSP cost.** For a pure-vision impulse the DSP block is trivial (image → tensor);
  if we ever add a heavy preprocessing/feature block, EI's data shows DSP can
  dominate total latency — keep vision preprocessing minimal.
  <https://docs.edgeimpulse.com/knowledge/metrics/inference-performance>

### Not a no-retrain lever, but worth noting

- Increasing network capacity to fight int8 quantization error is a documented
  accuracy lever but costs latency — the opposite direction for us.
  <https://docs.edgeimpulse.com/knowledge/guides/increasing-model-performance>

---

## Q5. UNO-Q-specific notes from the EI board page and related pages

- Board: Qualcomm Dragonwing **QRB2210**, "4 Arm Cortex-A cores and an Adreno 702
  GPU", Debian Linux, **aarch64 only** (`.eim` must be 64-bit).
  <https://docs.edgeimpulse.com/hardware/boards/arduino-uno-q>
- Run inference: connect a **USB** camera/mic, then `edge-impulse-linux-runner`
  (Studio compiles the `.eim`, downloads it, starts classifying). "Full hardware
  acceleration" is claimed but see Q1 — in practice CPU.
- App Lab integration: prebuilt "bricks" — Video Object Detection, Audio
  Classification, Keyword Spotting, Motion Detection — pick the model via env vars
  (`EI_OBJ_DETECTION_MODEL`, `EI_CLASSIFICATION_MODEL`, ...). Custom `.eim` goes in
  `/home/arduino/.arduino-bricks/ei-models/`. App runs as
  `cd /home/arduino/ArduinoApps/<app> && python3 main.py`.
  <https://docs.edgeimpulse.com/hardware/deployments/run-arduino-app-lab>
- Deployment targets offered for the board: "Linux aarch64" and "Linux Arduino
  UNO Q (GPU)". The GPU one is the one that fails to launch (Q1).
- **No official FPS / latency figure** is published for the UNO Q by Edge Impulse.
  Third-party (hackster OCR project, Marc Pous) notes the QRB2210 UNO Q is "too
  slow to handle heavy inference in real-time" and uses a model cascade / small
  FOMO stages — directionally consistent with our ~5.7 FPS.
  <https://www.hackster.io/marc-pous/ocr-on-arduino-uno-q-with-edge-impulse-using-model-cascade-5414f6>
  (page returns 403 to automated fetch; summary from search index / Q&A)
- Supported blocks: standard EI image blocks — image classification (MobileNet),
  FOMO object detection, plus audio/motion. No board-specific block restriction
  documented; the constraint is compute, not block support.
- The follow-on board **VENTUNO Q (Dragonwing IQ-8275)** has a real NPU and is
  where EI's accelerated Linux story actually lands.
  <https://www.edgeimpulse.com/blog/announcing-arduino-app-lab-full-integration-and-ventuno-q/>

---

## Recommended actions for EleTect X

1. **Stop trying to make the GPU `.eim` run.** Ship the CPU int8 EON `.eim`. It is
   the supported ceiling on this board. Budget ~5-7 FPS for a small model.
2. **Cut latency by model shape, not hardware:** FOMO (if not already), grayscale
   if the detector tolerates it, smallest input resolution that still separates
   elephant vs boar vs empty, lighter MobileNet alpha, confirm multi-thread
   XNNPACK, match camera resolution to model input.
3. **Lock night exposure by owning the camera.** Have our app open `/dev/video0`
   via V4L2, disable AGC (`auto_exposure=1`), pin `exposure_time_absolute ~ 256`
   and a fixed gain tuned to the IR illuminator, and feed frames to the model with
   `get_features_from_image()` + `classify()` (Python) or `edgeimpulsevideoinfer`
   (GStreamer). Do not rely on the runner's own camera path for exposure.
4. If we must keep the CLI runner's camera: force the camera onto `v4l2src` and
   pass `extra-controls="c,auto_exposure=1,exposure_time_absolute=256,..."` via
   `--gst-launch-args`; verify with `v4l2-ctl --get-ctrl` mid-stream that the
   sensor actually took the values.
5. Revisit acceleration only if the project moves to VENTUNO Q / an
   HTP-equipped Dragonwing board — then the QNN target and int8 → HTP path become
   real.

---

## Unverified / open

- **Exact default GStreamer pipeline** the UNO Q runner uses (v4l2src vs
  libcamerasrc by default, and the exact caps/JPEG stage). Needs
  `edge-impulse-linux --verbose` on the actual board. Forum evidence shows *both*
  paths appear depending on camera.
- **Whether the UNO Q's specific USB camera honors UVC manual exposure** at
  `auto_exposure=1` and holds it across stream restarts — camera-dependent, test
  with `v4l2-ctl`.
- **Whether `libcamerasrc` on the shipped UNO Q image exposes any manual-exposure
  property** — run `gst-inspect-1.0 libcamerasrc` on the board.
- **Precise EI runner behavior with `--force-engine` on the UNO Q** — whether it
  will refuse the GPU engine gracefully or still try to load
  `libtensorflowlite_gpu_delegate.so`. Not documented; test.
- **Mesa `rusticl` OpenCL on Turnip as a path for the TFLite GPU delegate** — in
  principle Mesa can now provide OpenCL on freedreno/Turnip, but (a) EI does not
  ship the GPU delegate `.so` for this target regardless, and (b) no report of
  anyone getting the TFLite GPU delegate working against rusticl on Adreno 702.
  Treated as not viable; not exhaustively disproven.
- **Any unreleased Arduino/Qualcomm package** adding FastRPC/QNN userland to the
  UNO Q image — the June 2026 forum questions to Arduino/EI staff are still
  unanswered as of this research; worth a periodic recheck of
  forum.arduino.cc and forum.edgeimpulse.com.
- **Official UNO Q inference benchmarks** from Edge Impulse — none published yet;
  our ~138 ms/frame is the working number.
- EON Compiler numeric ranges (25-65% RAM etc.) are MCU-framed in EI docs;
  the qualitative "faster than the TFLite interpreter, same accuracy" holds on
  Linux but exact Linux deltas are not published.
