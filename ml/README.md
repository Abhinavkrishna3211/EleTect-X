# ML — Off-Device Training

Training pipelines + datasets + evaluation. Runs on a PC, NOT the node. `seismic/` + `acoustic/` → **Edge Impulse** exports to `device/mcu/lib`; `vision/` → INT8 model to `device/mpu/models`. Keeps heavy training out of the flashable device code.
