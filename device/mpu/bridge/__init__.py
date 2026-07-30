"""Bridge RPC contract between the STM32 reflex layer and this MPU.

rpc.py holds the Python-side stubs matching device/mpu/bridge/schema.md,
one function per schema row, signatures and docstrings only - see that
module's own header for why no Bridge.provide()/Bridge.call() wiring exists
yet.
"""
