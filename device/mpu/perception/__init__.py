"""Vision INT8 detector (Adreno/OpenCL) and USB camera capture.

`camera.py` implements the IMX462 capture contract (open, capture, burst,
release) - see its own module docstring. `detector.py` runs the INT8 model
exported from the Edge Impulse vision project against those frames and
returns boxes in original-image pixel space; it does no capture of its own.
"""
