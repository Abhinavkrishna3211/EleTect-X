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

# Species partitioning (ADR 0034). Every row carries the species it belongs
# to, and every read filters on it, so one node learns one policy per
# species rather than one policy per node. Without this, a night of foxes
# raises the shared habituation context and ADR 0017's escalation floor
# hands the elephant arriving at dawn an already-escalated response it has
# never actually been habituated to.
#
# UNATTRIBUTED is the species of a trigger whose animal is not known yet,
# and of every row written before this column existed. It is never selected
# on: a read for a real species will not see these rows. That is deliberate
# and it does discard learned state on upgrade - see _migrate().
UNATTRIBUTED = ""

_SCHEMA = """
CREATE TABLE IF NOT EXISTS triggers (
    id INTEGER PRIMARY KEY,
    event_ts_s REAL NOT NULL,
    species TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_triggers_ts ON triggers (event_ts_s);
CREATE INDEX IF NOT EXISTS idx_triggers_species_ts ON triggers (species, event_ts_s);

CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    event_ts_s REAL NOT NULL,
    context INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    settled INTEGER NOT NULL DEFAULT 0,
    reward REAL,
    next_trigger_ts_s REAL,
    species TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_attempts_settled ON attempts (settled, event_ts_s);

CREATE TABLE IF NOT EXISTS action_values (
    species TEXT NOT NULL DEFAULT '',
    context INTEGER NOT NULL,
    tier INTEGER NOT NULL,
    value REAL NOT NULL,
    visits INTEGER NOT NULL,
    PRIMARY KEY (species, context, tier)
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
        visits: How many times this (species, context, tier) cell has now
            been scored. Not used by the selection policy - epsilon-greedy
            needs no visit counts - but kept because a value with one visit
            behind it and a value with fifty are not equally trustworthy,
            and nothing else records that.
        species: Which species' policy was credited - the species stored on
            the attempt when it was opened, not the species of the trigger
            that settled it. Defaults to UNATTRIBUTED so a caller
            constructing one of these for a test need not care.
    """

    context: int
    tier: Tier
    gap_s: float
    reward: float
    value: float
    visits: int
    species: str = UNATTRIBUTED


def _migrate(connection: sqlite3.Connection) -> None:
    """Bring a pre-species database up to the current schema, in place.

    CREATE TABLE IF NOT EXISTS does nothing to a table that already exists,
    so a database written before ADR 0034 keeps its old columns and every
    species-filtered query silently returns nothing. This closes that by
    adding the column where SQLite allows it and rebuilding where it does
    not.

    `triggers` and `attempts` take a plain ADD COLUMN. `action_values`
    cannot: its primary key has to grow a column, and SQLite has no ALTER
    for that, so the table is rebuilt and its rows copied across.

    **Existing rows become UNATTRIBUTED and are never read again.** They
    are not assigned to a species, because nothing in the old schema records
    which animal drove them - under the "both" scope in particular, the rows
    are a mix of elephant and boar responses with no way to separate them.
    Attributing them to a guess would launder invented provenance into a
    policy that decides whether a horn fires at a real animal. They are kept
    rather than deleted so the history stays inspectable off-device.

    In practice few nodes hit this path at all: services/config.py keys the
    database filename on the deterrence scope, so a node moving from
    "elephant_only" to a multi-species scope opens a fresh file with the
    current schema and has nothing to migrate. This is for a node whose
    scope string does not change across the upgrade.

    Idempotent, and safe to run on a database already at the current
    schema - both branches check before acting.
    """
    def columns(table: str) -> set[str]:
        return {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }

    for table in ("triggers", "attempts"):
        if "species" not in columns(table):
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN species TEXT NOT NULL DEFAULT ''"
            )

    if "species" not in columns("action_values"):
        connection.executescript(
            """
            ALTER TABLE action_values RENAME TO action_values_pre_species;
            CREATE TABLE action_values (
                species TEXT NOT NULL DEFAULT '',
                context INTEGER NOT NULL,
                tier INTEGER NOT NULL,
                value REAL NOT NULL,
                visits INTEGER NOT NULL,
                PRIMARY KEY (species, context, tier)
            );
            INSERT INTO action_values (species, context, tier, value, visits)
                SELECT '', context, tier, value, visits
                FROM action_values_pre_species;
            DROP TABLE action_values_pre_species;
            """
        )


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
        _migrate(connection)
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
            this one - 0 for an isolated event. Species-blind, and consumed
            only by _watch_length_s(): looking longer is cheap, escalating
            is not, so the watch keeps the node-level count while the
            escalation floor uses repeat_count()'s species-scoped one
            (ADR 0034).

            The upper bound is inclusive and must stay that way: the count
            runs before the INSERT, so this event's own row is not in it,
            while a PRIOR trigger sharing this one's exact timestamp is a
            real repeat that has to be counted. Those ties are not
            hypothetical - time.time() is a ~15.6 ms-granular system clock
            on some hosts, and two triggers inside one tick read as equal.
            repeat_count() therefore excludes this event's own row by rowid
            rather than by timestamp; see there.
        """
        connection = self._connect()
        repeats = connection.execute(
            "SELECT COUNT(*) FROM triggers WHERE event_ts_s >= ? AND event_ts_s <= ?",
            (event_ts_s - window_s, event_ts_s),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO triggers (event_ts_s, species) VALUES (?, ?)",
            (event_ts_s, UNATTRIBUTED),
        )
        connection.commit()
        return int(repeats)

    def attribute_trigger(self, event_ts_s: float, species: str) -> int:
        """Name the animal behind a trigger already recorded, after the fact.

        record_trigger() runs on the seismic footfall, before the camera has
        said anything, so the species is genuinely unknown at that point and
        the row goes in UNATTRIBUTED. This is the second half: once the
        vision check has confirmed a label, the trigger it belongs to gets
        named, and only then does it count toward that species' habituation
        window.

        A trigger that is never confirmed stays UNATTRIBUTED forever and
        counts toward no species. That is the intended behaviour and it is a
        real change from the node-level scheme: an unconfirmed crossing no
        longer escalates anybody's tier floor. The old comment on
        record_trigger() argued the opposite - that any repeated crossing is
        a habituation signal - and that argument does not survive per-species
        state, because an unattributed crossing cannot say WHOSE habituation
        it is evidence of.

        Matches on the exact timestamp record_trigger() was given, which the
        reflex loop already carries as the event's wall clock, and names the
        NEWEST unattributed row at that timestamp - the one this event
        inserted. Two triggers can share a timestamp on a coarse system
        clock (see record_trigger()), and naming both would credit one
        animal with a crossing it did not make. Never blocks past one
        UPDATE.

        Returns:
            How many rows were named - 1 normally, 0 if the timestamp does
            not match a stored unattributed trigger, which is a caller bug
            rather than a field condition and is logged by the caller, not
            raised here.
        """
        connection = self._connect()
        cursor = connection.execute(
            "UPDATE triggers SET species = ? WHERE id = ("
            "SELECT MAX(id) FROM triggers WHERE event_ts_s = ? AND species = ?)",
            (species, event_ts_s, UNATTRIBUTED),
        )
        connection.commit()
        return int(cursor.rowcount)

    def repeat_count(self, event_ts_s: float, window_s: float, species: str) -> int:
        """How many triggers of one species precede `event_ts_s` in the window.

        The per-species replacement for record_trigger()'s return value, read
        at tier-selection time rather than at trigger time because that is
        the first moment the species is known. Feeds
        cognition.bandit.habituation_context().

        Runs after attribute_trigger() has named this event's own row, so
        that row has to be kept out of its own count - an isolated first
        sighting must report 0, exactly as record_trigger() does. It is
        excluded by rowid, not by timestamp: an earlier trigger sharing this
        one's wall clock is a genuine repeat, and a `< event_ts_s` bound
        would silently drop it whenever the system clock is coarse enough
        for two triggers to land in one tick.

        The rowid bound is COALESCEd so a timestamp that was never recorded
        still counts the whole window rather than returning 0 - that case is
        a caller bug, and answering "no repeats" would hide it behind a
        plausible number.
        """
        connection = self._connect()
        count = connection.execute(
            "SELECT COUNT(*) FROM triggers WHERE species = ? "
            "AND event_ts_s >= ? AND event_ts_s <= ? "
            "AND id < COALESCE("
            "(SELECT MAX(id) FROM triggers WHERE event_ts_s = ?), 0x7FFFFFFFFFFFFFFF)",
            (species, event_ts_s - window_s, event_ts_s, event_ts_s),
        ).fetchone()[0]
        return int(count)

    def action_values(self, species: str = UNATTRIBUTED) -> dict[tuple[int, Tier], float]:
        """Load one species' learned action values, keyed for select_tier().

        Never blocks past one SELECT over a table bounded by
        (context buckets x tiers) rows - single digits, so this is read
        fresh per event rather than cached behind an invalidation rule
        nothing would exercise.

        Args:
            species: Whose policy to load. Defaults to UNATTRIBUTED, which
                is a real partition and not a wildcard - it holds the rows
                written for triggers the camera never named, plus every row
                migrated from the pre-species schema.

        Returns:
            {(context, Tier): value} for that species. Pairs never visited
            are absent, which select_tier() reads as 0.0.
        """
        connection = self._connect()
        rows = connection.execute(
            "SELECT context, tier, value FROM action_values WHERE species = ?",
            (species,),
        ).fetchall()
        return {(int(context), Tier(tier)): float(value) for context, tier, value in rows}

    def record_attempt(
        self, event_ts_s: float, context: int, tier: Tier, species: str = UNATTRIBUTED
    ) -> None:
        """Open an unsettled attempt for a deterrence that actually fired.

        Only ever called on a true actuator ack - see the module docstring.
        Never blocks past one INSERT.

        Args:
            event_ts_s: Wall-clock timestamp the deterrence fired at.
            context: Context the tier was chosen in.
            tier: The tier that fired.
            species: Whose policy this attempt belongs to. Stored on the
                row so settle_pending() can credit the right cell later -
                the trigger that eventually settles it may well be a
                different animal. Defaults to UNATTRIBUTED.
        """
        connection = self._connect()
        connection.execute(
            "INSERT INTO attempts (event_ts_s, context, tier, species) "
            "VALUES (?, ?, ?, ?)",
            (event_ts_s, int(context), int(tier), species),
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

        The reward stays node-level on purpose (ADR 0034). proxy_reward()
        measures the quiet before the next seismic trigger, and a trigger is
        species-blind until the camera resolves it - most night triggers
        never are. Settling only against a same-species trigger would
        therefore stall learning exactly when the node works hardest. So any
        trigger settles the pending attempt, and the credit goes to the
        species stored on the ATTEMPT, not to the species of the trigger
        that settled it. The cost is real and documented in
        docs/KNOWN_GAPS.md: a boar walking past shortly after an elephant
        was deterred reads as that deterrence having failed.

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
            "SELECT id, event_ts_s, context, tier, species FROM attempts "
            "WHERE settled = 0 ORDER BY event_ts_s LIMIT 1"
        ).fetchone()
        if row is None:
            return None

        attempt_id, event_ts_s, context, tier_value, species = row
        context = int(context)
        species = str(species)
        tier = Tier(tier_value)
        gap_s = now_ts_s - float(event_ts_s)
        reward = proxy_reward(gap_s, params.reward_horizon_s)

        stored = connection.execute(
            "SELECT value, visits FROM action_values "
            "WHERE species = ? AND context = ? AND tier = ?",
            (species, context, int(tier)),
        ).fetchone()
        old_value = float(stored[0]) if stored is not None else 0.0
        visits = (int(stored[1]) if stored is not None else 0) + 1
        value = updated_value(old_value, reward, params.step_size)

        connection.execute(
            "INSERT INTO action_values (species, context, tier, value, visits) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(species, context, tier) DO UPDATE SET value = excluded.value, "
            "visits = excluded.visits",
            (species, context, int(tier), value, visits),
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
            species=species,
        )

    def close(self) -> None:
        """Release the connection; idempotent, like Camera.close().

        Safe to call on a store that was never used - there is nothing to
        close until the first real operation opened something.
        """
        if self._connection is not None:
            self._connection.close()
            self._connection = None
