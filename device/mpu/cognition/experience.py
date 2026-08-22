"""SQLite experience store - the bandit's persistence, and its only I/O.

CONTEXT.md 4's "SQLite experience" and the store services/config.py has
reserved a path for since before cognition/ existed ("Created by cognition/
once that module lands; only the path is fixed here"). Learning that does
not survive a restart is not learning: the MPU suspends between events by
design (ADR 0008), so anything held only in process memory would be lost on
roughly the timescale the bandit is supposed to learn over.

This module is the I/O edge (ENGINEERING_CONVENTIONS.md 2 layer 4). It owns
every sqlite3 call in the MPU tree and holds no policy: reward shaping and
action-value updates come from cognition/bandit.py's pure functions, which
this module calls but never reimplements.

__init__ does no I/O at all - the connection, the schema, and the parent
directory are created on first real use. That is the same property
perception/camera.Camera has and that device/mpu/main.py already relies on
when it constructs one at module scope, before the board's hardware or
filesystem state is confirmed.

Two behaviours worth knowing before reading the methods:

- **An attempt is recorded only when the deterrence actually fired.** The
  MCU refuses a request inside its own cooldown (rule_gate_apply() returns
  allowed=false, which is exactly the bool the Bridge acks back), and
  SAFE_MODE fires nothing at all. Crediting either case would teach the
  bandit about actions that never happened, so services/reflex_loop.py only
  calls record_attempt() on a true horn ack.
- **An attempt is settled by the NEXT trigger, not by a timer.** The reward
  is quiet time (cognition/bandit.proxy_reward), so it is not knowable until
  the quiet ends. The consequence is a real survivorship bias: an attempt
  followed by permanent silence - the best possible outcome - is never
  scored at all. Documented in docs/KNOWN_GAPS.md rather than papered over
  with an invented timeout reward.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cognition.bandit import BanditParams, Tier, proxy_reward, updated_value
from services import config as services_config

# sqlite3's own reserved name for a private, process-lifetime database. Used
# by tests and by bench/demo_replay.py so a dry run never writes real
# learning state; recognised here only to skip the mkdir a real path needs.
IN_MEMORY_PATH = Path(":memory:")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY,
    event_ts_s REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_triggers_ts ON triggers (event_ts_s);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    event_ts_s REAL NOT NULL,
    context INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    reward REAL,
    next_trigger_ts_s REAL
);
CREATE INDEX IF NOT EXISTS idx_attempts_settled ON attempts (settled, event_ts_s);

CREATE TABLE IF NOT EXISTS action_values (
    context INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    value REAL NOT NULL,
    visits INTEGER NOT NULL,
    PRIMARY KEY (context, tier)
);
"""


@dataclass(frozen=True)
class SettledAttempt:
    """What one settle_pending() call scored, returned for logging/tests.

    Attributes:
        context: The context the settled attempt was chosen in.
        tier: The tier that fired.
        gap_s: Seconds of quiet between that firing and the trigger that
            settled it.
        reward: proxy_reward(gap_s, ...) - see that function on why this is
            a proxy and not an outcome.
        value: The action value after updated_value() was applied.
        visits: How many times this (context, tier) pair has now been
            scored. Not used by the selection policy - epsilon-greedy needs
            no visit counts - but kept because a value with one visit behind
            it and a value with fifty are not equally trustworthy, and
            nothing else records that.
    """

    context: int
    tier: Tier
    gap_s: float
    reward: float
    value: float
    visits: int


class ExperienceStore:
    """Persistent action values and event history for the deterrence bandit.

    Not thread-safe and not intended to be: the MPU's event path is a single
    Bridge-driven callback (device/mpu/main.py), so one connection owned by
    one caller is the whole concurrency story.
    """

    def __init__(self, db_path: Path = services_config.EXPERIENCE_DB_PATH):
        """Record where the database lives; open nothing.

        Never blocks and never touches the filesystem - see the module
        docstring on why construction stays I/O-free.

        Args:
            db_path: Where to store the database. Defaults to
                services.config.EXPERIENCE_DB_PATH, the path that module has
                always reserved for it. Pass IN_MEMORY_PATH for a store that
                writes nothing.
        """
        self._db_path = db_path
        self._connection: sqlite3.Connection | None = None

    @property
    def db_path(self) -> Path:
        """Where this store reads and writes; fixed at construction."""
        return self._db_path

    def _connect(self) -> sqlite3.Connection:
        """Open the connection and ensure the schema exists; idempotent.

        Creates the parent directory if missing - services/config.py fixes
        DATA_DIR's path but explicitly leaves its creation to this module,
        and nothing else in the tree creates it. Blocks only for the open
        and the CREATE TABLE IF NOT EXISTS batch, both one-time per process.
        """
        if self._connection is not None:
            return self._connection
        if self._db_path != IN_MEMORY_PATH:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(self._db_path))
        connection.executescript(_SCHEMA)
        connection.commit()
        self._connection = connection
        return connection

    def record_trigger(self, event_ts_s: float, window_s: float) -> int:
        """Log one trigger and report how many preceded it inside the window.

        Called for every footfall event, not only alerting ones: a repeated
        STA/LTA crossing is the habituation signal regardless of what fusion
        made of it, and an animal circling a node that keeps not clearing
        the alert threshold is exactly the case the context bucket should
        notice.

        Never blocks past one INSERT and one COUNT.

        Args:
            event_ts_s: Wall-clock timestamp of this trigger. Wall clock,
                not monotonic, because it has to stay comparable across the
                MPU suspend/resume cycles ADR 0008 describes - the same
                reason perception/storage.CaptureEventTag uses wall clock.
            window_s: How far back a prior trigger still counts as a repeat.

        Returns:
            The number of triggers already stored within window_s before
            this one - 0 for an isolated event. Feeds
            cognition.bandit.habituation_context().
        """
        connection = self._connect()
        repeats = connection.execute(
            "SELECT COUNT(*) FROM triggers WHERE event_ts_s >= ? AND event_ts_s <= ?",
            (event_ts_s - window_s, event_ts_s),
        ).fetchone()[0]
        connection.execute("INSERT INTO triggers (event_ts_s) VALUES (?)", (event_ts_s,))
        connection.commit()
        return int(repeats)

    def action_values(self) -> dict[tuple[int, Tier], float]:
        """Load every learned action value, keyed for select_tier().

        Never blocks past one SELECT over a table bounded by
        (context buckets x tiers) rows - single digits, so this is read
        fresh per event rather than cached behind an invalidation rule
        nothing would exercise.

        Returns:
            {(context, Tier): value}. Pairs never visited are absent, which
            select_tier() reads as 0.0.
        """
        connection = self._connect()
        rows = connection.execute("SELECT context, tier, value FROM action_values").fetchall()
        return {(int(context), Tier(tier)): float(value) for context, tier, value in rows}

    def record_attempt(self, event_ts_s: float, context: int, tier: Tier) -> None:
        """Open an unsettled attempt for a deterrence that actually fired.

        Only ever called on a true actuator ack - see the module docstring.
        Never blocks past one INSERT.

        Args:
            event_ts_s: Wall-clock timestamp the deterrence fired at.
            context: Context the tier was chosen in.
            tier: The tier that fired.
        """
        connection = self._connect()
        connection.execute(
            "INSERT INTO attempts (event_ts_s, context, tier) VALUES (?, ?, ?)",
            (event_ts_s, int(context), int(tier)),
        )
        connection.commit()

    def settle_pending(self, now_ts_s: float, params: BanditParams) -> SettledAttempt | None:
        """Score the oldest unsettled attempt against the quiet that followed it.

        Called at the top of each event, before selection, so the values
        select_tier() reads already include what the current trigger just
        revealed about the previous response.

        Settles exactly one attempt per call - the oldest. More than one
        pending attempt should not arise (each is settled by the next
        trigger, and every trigger calls this), so draining a backlog here
        would be handling a state this module cannot otherwise reach; taking
        the oldest keeps the reward attributable to a specific gap rather
        than to an ambiguous merged interval.

        Never blocks past a handful of single-row statements.

        Args:
            now_ts_s: Wall-clock timestamp of the trigger doing the
                settling.
            params: Supplies reward_horizon_s and step_size.

        Returns:
            A SettledAttempt describing what was scored, or None if nothing
            was pending.
        """
        connection = self._connect()
        row = connection.execute(
            "SELECT id, event_ts_s, context, tier FROM attempts "
            "WHERE settled = 0 ORDER BY event_ts_s LIMIT 1"
        ).fetchone()
        if row is None:
            return None

        attempt_id, event_ts_s, context, tier_value = row
        context = int(context)
        tier = Tier(tier_value)
        gap_s = now_ts_s - float(event_ts_s)
        reward = proxy_reward(gap_s, params.reward_horizon_s)

        stored = connection.execute(
            "SELECT value, visits FROM action_values WHERE context = ? AND tier = ?",
            (context, int(tier)),
        ).fetchone()
        old_value = float(stored[0]) if stored is not None else 0.0
        visits = (int(stored[1]) if stored is not None else 0) + 1
        value = updated_value(old_value, reward, params.step_size)

        connection.execute(
            "INSERT INTO action_values (context, tier, value, visits) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(context, tier) DO UPDATE SET value = excluded.value, "
            "visits = excluded.visits",
            (context, int(tier), value, visits),
        )
        connection.execute(
            "UPDATE attempts SET settled = 1, reward = ?, next_trigger_ts_s = ? WHERE id = ?",
            (reward, now_ts_s, attempt_id),
        )
        connection.commit()

        return SettledAttempt(
            context=context,
            tier=tier,
            gap_s=gap_s,
            reward=reward,
            value=value,
            visits=visits,
        )

    def close(self) -> None:
        """Release the connection; idempotent, like Camera.close().

        Safe to call on a store that was never used - there is nothing to
        close until the first real operation opened something.
        """
        if self._connection is not None:
            self._connection.close()
            self._connection = None
