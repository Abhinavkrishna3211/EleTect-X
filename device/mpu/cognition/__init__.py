"""Log-odds fusion, contextual-bandit deterrence, SQLite experience store.

`fusion.py` implements the fusion formula `L = L_prior + sum(a_i * w_i *
(l_i - l0_i))`, `P = sigmoid(L)` (CONTEXT.md 4) as a pure function over
plain floats, with `config.py` holding its weights/baselines/prior - see
their own module docstrings. The contextual bandit's action-value update and
the SQLite experience store are not built yet: populated in a future build
call, once a Bridge-delivered event actually reaches this package.
"""
