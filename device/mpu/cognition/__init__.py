"""Log-odds fusion, contextual-bandit deterrence, SQLite experience store.

`fusion.py` implements the fusion formula `L = L_prior + sum(a_i * w_i *
(l_i - l0_i))`, `P = sigmoid(L)` (CONTEXT.md 4) as a pure function over
plain floats; `decision.py` turns `P` into an alert; `bandit.py` picks which
of three deterrence tiers to fire, epsilon-greedily and with a hard
escalation floor on repeat triggers; `experience.py` persists that learning
in SQLite so it survives the suspend/resume cycle. `config.py` holds every
tuning value the other four need - see their own module docstrings.

One honest boundary on all of that: the bandit learns against an
unvalidated proxy reward (quiet time since the last firing), not against
any measured animal outcome, because nothing on this device observes one.
`bandit.proxy_reward()` and docs/KNOWN_GAPS.md both say so at length.
"""
