"""Log-odds fusion, contextual-bandit deterrence, SQLite experience store.

Empty scaffold - populated in a future build call. Owns the fusion formula
`L = L_prior + sum(a_i * w_i * (l_i - l0_i))`, `P = sigmoid(L)` (CONTEXT.md
4) and the bandit's action-value update - both pure functions over plain
arrays/floats, no Bridge or SQLite calls inside the function body itself
(ENGINEERING_CONVENTIONS.md 2).
"""
