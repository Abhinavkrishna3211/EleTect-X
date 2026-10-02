# Stub SDK headers for the syntax check

`panns_logmel.cpp` cannot be compiled without the Edge Impulse inferencing
SDK, and the SDK only arrives with a Studio export. That is a poor reason to
leave the one file that actually ships unbuilt until an integrator tries it —
the first attempt at this port compiled its own core cleanly and still would
have failed in the SDK, because the `EIDSP_*` status enumerators live in
namespace `ei` and had not been imported.

`../syntax_check.sh` builds a minimal include tree from these stubs plus the
two real headers that define the contract, and compiles the block against it.

The real headers are fetched at run time rather than vendored: they are
copyright Edge Impulse and carry their Terms of Service, and this repository
should not redistribute them. Everything in this directory is our own, and
only declares what `panns_logmel.cpp` touches.

`model_metadata.h` is the interesting one. Studio generates
`ei_dsp_config_panns_logmel_t` from `../../parameters.json`, one field per
`param`. The copy here is written to match. If a parameter is renamed in
Studio without updating it, this check keeps passing while the real build
breaks — so treat the two as a pair.

## What this check does not cover

The first real `.eim` build found two things this tree had been getting
wrong, and both are worth stating plainly, because a green syntax check is
easy to read as more assurance than it is.

The struct was stubbed into `model_variables.h`. Studio puts it in
`model_metadata.h`. The block compiled either way — it includes both — so
nothing ever contradicted the guess.

There is no stub for `model_variables.h` at all now, and that is deliberate
rather than an omission. The real one is where Studio writes the forward
declaration of `extract_panns_logmel_features`, but it also *defines* the
config instance, the label table and the DSP block array, so a second
translation unit that includes it is a duplicate-definition link error. The
shim therefore does not include it, and a stub nothing includes would only
invite someone to keep it in step for no reason. The consequence is that
this check cannot verify the function's signature against the one Studio
declares; the link is what does that, and it does it properly — a signature
that drifts becomes an undefined reference when the `.eim` is linked.

More generally: this check compiles one translation unit. It says the block
is valid C++ against the SDK's types. It says nothing about whether the
block links, runs, or computes the right numbers. Those are
`parity_cpp.py`, `parity_resample.py`, and a built `.eim` scored over the
test split.
