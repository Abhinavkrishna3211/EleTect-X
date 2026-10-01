"""Tests for cognition/experience.py against real SQLite, not a fake.

These use pytest's tmp_path and a genuine on-disk database. Mocking sqlite3
here would test nothing worth testing: the whole reason this module exists is
that the bandit's learning has to survive a process restart, and a mock that
returns whatever it was told to return cannot demonstrate that. The
round-trip test below closes the store, constructs a completely new one
against the same path, and reads the values back - the closest thing to a
real restart a host test can do.

Rewards and updated values are hand-computed literals, never re-derived by
calling cognition/bandit.py's functions in the test body
(ENGINEERING_CONVENTIONS.md 4).
"""

import sqlite3
import threading

import pytest

from cognition.bandit import BanditParams, Tier
from cognition.experience import IN_MEMORY_PATH, ExperienceStore

# reward_horizon_s of 1000.0 makes every expected reward below a clean
# fraction: a 250s gap is 0.25 exactly, with no float noise to approximate
# around. step_size 0.2 gives the same property for the value updates.
PARAMS = BanditParams(
    epsilon=0.0,
    step_size=0.2,
    habituation_window_s=600.0,
    tier_floor_by_context=(Tier.TIER_1, Tier.TIER_2, Tier.TIER_3),
    reward_horizon_s=1000.0,
)


def _store(tmp_path):
    """Build a store under a nested, not-yet-created directory.

    Nested on purpose: services/config.py fixes DATA_DIR's path but leaves
    its creation to this module, and on a fresh board that directory does not
    exist yet.
    """
    return ExperienceStore(tmp_path / "data" / "experience.sqlite3")


# ---------------------------------------------------------------------------
# Construction and lazy I/O
# ---------------------------------------------------------------------------


def test_construction_creates_nothing_on_disk(tmp_path):
    """__init__ must do no I/O - device/mpu/main.py constructs one at import.

    If construction created the database, importing main.py on a board with
    an unwritable or not-yet-mounted data partition would fail at import
    time rather than at first event.
    """
    store = _store(tmp_path)
    assert not store.db_path.exists()
    assert not store.db_path.parent.exists()


def test_first_use_creates_the_parent_directory_and_the_database(tmp_path):
    """The data directory is created on demand; nothing else in the tree makes it."""
    store = _store(tmp_path)
    store.record_trigger(1000.0, 600.0)
    assert store.db_path.exists()
    store.close()


def test_close_is_idempotent_and_safe_on_an_unused_store(tmp_path):
    """close() on a never-opened store must not raise - nothing was opened."""
    store = _store(tmp_path)
    store.close()
    store.close()
    assert not store.db_path.exists()


def test_in_memory_store_writes_nothing_to_disk(tmp_path, monkeypatch):
    """The bench replay's store must leave no file behind anywhere.

    monkeypatch.chdir guards the one way :memory: could still produce a
    file - a path resolved relative to the working directory - by making
    that directory an empty temporary one and asserting it stays empty.
    """
    monkeypatch.chdir(tmp_path)
    store = ExperienceStore(IN_MEMORY_PATH)
    store.record_trigger(1000.0, 600.0)
    store.record_attempt(1000.0, 0, Tier.TIER_1)
    store.settle_pending(1250.0, PARAMS)
    store.close()
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# record_trigger - the habituation window
# ---------------------------------------------------------------------------


def test_first_trigger_reports_no_repeats(tmp_path):
    """An empty store must report 0 repeats, which is context 0."""
    store = _store(tmp_path)
    assert store.record_trigger(1000.0, 600.0) == 0
    store.close()


def test_repeat_count_grows_with_triggers_inside_the_window(tmp_path):
    """Three triggers a minute apart read as 0, 1, then 2 repeats."""
    store = _store(tmp_path)
    counts = [
        store.record_trigger(1000.0, 600.0),
        store.record_trigger(1060.0, 600.0),
        store.record_trigger(1120.0, 600.0),
    ]
    assert counts == [0, 1, 2]
    store.close()


def test_triggers_outside_the_window_are_not_counted(tmp_path):
    """A trigger older than window_s must not inflate the repeat count.

    This is what makes the escalation de-escalate on its own: the ladder
    resets not by a decay rule but by old events aging out of the window.
    """
    store = _store(tmp_path)
    store.record_trigger(1000.0, 600.0)
    assert store.record_trigger(1700.0, 600.0) == 0
    store.close()


def test_the_window_boundary_is_inclusive(tmp_path):
    """A trigger exactly window_s old still counts - the boundary is closed.

    Asserted explicitly because "exactly at the edge" is the one case an
    off-by-one in the query would change, and it is otherwise invisible.
    """
    store = _store(tmp_path)
    store.record_trigger(1000.0, 600.0)
    assert store.record_trigger(1600.0, 600.0) == 1
    store.close()


def test_every_trigger_is_recorded_regardless_of_alerting(tmp_path):
    """The store counts triggers, not alerts - it is never told about decisions.

    Asserted at the API level: record_trigger takes no alert flag, so a
    sub-threshold event that reflex_loop passes through still accumulates
    toward habituation.
    """
    store = _store(tmp_path)
    for i in range(5):
        store.record_trigger(1000.0 + i, 600.0)
    assert store.record_trigger(1005.0, 600.0) == 5
    store.close()


# ---------------------------------------------------------------------------
# settle_pending
# ---------------------------------------------------------------------------


def test_nothing_pending_settles_to_none(tmp_path):
    """With no recorded attempt there is nothing to score."""
    store = _store(tmp_path)
    assert store.settle_pending(1000.0, PARAMS) is None
    store.close()


def test_settlement_scores_the_real_gap_and_updates_the_right_cell(tmp_path):
    """A 250s gap at a 1000s horizon is reward 0.25; from 0.0 at alpha 0.2 that is 0.05.

    Both numbers are hand-computed: 250/1000 = 0.25, and
    0.0 + 0.2 * (0.25 - 0.0) = 0.05.
    """
    store = _store(tmp_path)
    store.record_attempt(1000.0, 1, Tier.TIER_2)
    settled = store.settle_pending(1250.0, PARAMS)

    assert settled is not None
    assert settled.context == 1
    assert settled.tier is Tier.TIER_2
    assert settled.gap_s == pytest.approx(250.0)
    assert settled.reward == pytest.approx(0.25)
    assert settled.value == pytest.approx(0.05)
    assert settled.visits == 1
    assert store.action_values() == {(1, Tier.TIER_2): pytest.approx(0.05)}
    store.close()


def test_an_attempt_settles_exactly_once(tmp_path):
    """A settled attempt must not be re-scored by the next trigger.

    Double-settling would let one deterrence event move an action value
    twice, weighting it against every other event for no reason.
    """
    store = _store(tmp_path)
    store.record_attempt(1000.0, 0, Tier.TIER_1)
    store.settle_pending(1250.0, PARAMS)
    assert store.settle_pending(1500.0, PARAMS) is None
    store.close()


def test_settlement_takes_the_oldest_pending_attempt_first(tmp_path):
    """Two pending attempts settle oldest-first, so gaps stay attributable."""
    store = _store(tmp_path)
    store.record_attempt(1000.0, 0, Tier.TIER_1)
    store.record_attempt(1100.0, 2, Tier.TIER_3)

    first = store.settle_pending(1200.0, PARAMS)
    assert first is not None
    assert first.tier is Tier.TIER_1
    assert first.gap_s == pytest.approx(200.0)

    second = store.settle_pending(1300.0, PARAMS)
    assert second is not None
    assert second.tier is Tier.TIER_3
    assert second.gap_s == pytest.approx(200.0)
    store.close()


def test_visits_accumulate_across_settlements_of_the_same_cell(tmp_path):
    """The same (context, tier) scored twice must report 2 visits, not 1."""
    store = _store(tmp_path)
    store.record_attempt(1000.0, 0, Tier.TIER_1)
    store.settle_pending(1250.0, PARAMS)
    store.record_attempt(1300.0, 0, Tier.TIER_1)
    settled = store.settle_pending(1550.0, PARAMS)

    assert settled is not None
    assert settled.visits == 2
    store.close()


def test_a_second_settlement_compounds_on_the_stored_value(tmp_path):
    """Two 0.25 rewards at alpha 0.2 give 0.05 then 0.09, hand-computed.

    0.05 + 0.2 * (0.25 - 0.05) = 0.05 + 0.04 = 0.09. This is the assertion
    that the update reads the stored value rather than starting from zero
    each time - a bug that would leave the bandit permanently unable to
    learn anything past one event's worth.
    """
    store = _store(tmp_path)
    store.record_attempt(1000.0, 0, Tier.TIER_1)
    store.settle_pending(1250.0, PARAMS)
    store.record_attempt(1300.0, 0, Tier.TIER_1)
    settled = store.settle_pending(1550.0, PARAMS)

    assert settled is not None
    assert settled.value == pytest.approx(0.09)
    store.close()


def test_a_long_quiet_period_earns_the_full_reward(tmp_path):
    """Quiet past the horizon saturates: reward 1.0, value 0.0 -> 0.2 at alpha 0.2."""
    store = _store(tmp_path)
    store.record_attempt(1000.0, 2, Tier.TIER_3)
    settled = store.settle_pending(9000.0, PARAMS)

    assert settled is not None
    assert settled.reward == pytest.approx(1.0)
    assert settled.value == pytest.approx(0.2)
    store.close()


def test_action_values_are_empty_before_anything_settles(tmp_path):
    """An unsettled attempt teaches nothing yet - the reward is not known.

    Values must appear only at settlement, never at record_attempt time:
    crediting an attempt when it fires would score it before its outcome
    exists.
    """
    store = _store(tmp_path)
    store.record_attempt(1000.0, 0, Tier.TIER_1)
    assert store.action_values() == {}
    store.close()


# ---------------------------------------------------------------------------
# Persistence across a restart
# ---------------------------------------------------------------------------


def test_learned_values_survive_close_and_reopen(tmp_path):
    """The round trip this module exists for: a new store reads the old one's learning.

    Constructs a second ExperienceStore against the same path rather than
    reusing the first - reusing it would prove only that a live connection
    remembers its own writes, which is not the property under test.
    """
    db_path = tmp_path / "data" / "experience.sqlite3"

    first = ExperienceStore(db_path)
    first.record_attempt(1000.0, 1, Tier.TIER_2)
    first.settle_pending(1250.0, PARAMS)
    first.close()

    second = ExperienceStore(db_path)
    assert second.action_values() == {(1, Tier.TIER_2): pytest.approx(0.05)}
    second.close()


def test_visit_counts_survive_a_restart(tmp_path):
    """Visit counts persist too, so a reopened store keeps accumulating them."""
    db_path = tmp_path / "data" / "experience.sqlite3"

    first = ExperienceStore(db_path)
    first.record_attempt(1000.0, 0, Tier.TIER_1)
    first.settle_pending(1250.0, PARAMS)
    first.close()

    second = ExperienceStore(db_path)
    second.record_attempt(1300.0, 0, Tier.TIER_1)
    settled = second.settle_pending(1550.0, PARAMS)
    assert settled is not None
    assert settled.visits == 2
    second.close()


def test_trigger_history_survives_a_restart(tmp_path):
    """Habituation context must not reset just because the process did.

    An MPU that suspends between events (ADR 0008) would otherwise treat
    every trigger as a first trigger, and the escalation floor would never
    engage in the field at all.
    """
    db_path = tmp_path / "data" / "experience.sqlite3"

    first = ExperienceStore(db_path)
    first.record_trigger(1000.0, 600.0)
    first.close()

    second = ExperienceStore(db_path)
    assert second.record_trigger(1060.0, 600.0) == 1
    second.close()


def test_an_unsettled_attempt_survives_a_restart_and_still_settles(tmp_path):
    """An attempt pending across a restart is scored by the trigger that follows it.

    The realistic case, not an exotic one: the MPU suspends after firing, so
    almost every attempt is settled by a different process run than the one
    that opened it.
    """
    db_path = tmp_path / "data" / "experience.sqlite3"

    first = ExperienceStore(db_path)
    first.record_attempt(1000.0, 2, Tier.TIER_3)
    first.close()

    second = ExperienceStore(db_path)
    settled = second.settle_pending(1500.0, PARAMS)
    assert settled is not None
    assert settled.tier is Tier.TIER_3
    assert settled.reward == pytest.approx(0.5)
    second.close()


def test_reopening_does_not_wipe_the_existing_schema(tmp_path):
    """CREATE TABLE IF NOT EXISTS must be a no-op, not a reset.

    Reads the raw table with sqlite3 directly rather than through the store,
    so a bug that dropped and recreated tables on open could not hide behind
    the store's own accessor.
    """
    db_path = tmp_path / "data" / "experience.sqlite3"

    first = ExperienceStore(db_path)
    first.record_trigger(1000.0, 600.0)
    first.close()

    second = ExperienceStore(db_path)
    second.record_trigger(1060.0, 600.0)
    second.close()

    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute("SELECT COUNT(*) FROM triggers").fetchone()[0]
    finally:
        connection.close()
    assert rows == 2


# --- thread safety -----------------------------------------------------------


def test_a_second_thread_can_use_a_store_the_first_thread_opened(tmp_path):
    """The sqlite3.ProgrammingError that cost HOME_TEST_MODE encounters silently.

    device/mpu/main.py binds one store into _footfall_kwargs, and two
    threads reach it through that dict: the Bridge callback serving
    report_footfall_event, and home_test.py's deterrence worker. Whichever
    arrived first owned the connection; the other used to be refused
    outright by sqlite3's check_same_thread, inside a broad except that
    turned the refusal into a missing deterrence rather than a crash.

    Opened from this thread deliberately - calling _connect() lazily from
    the worker would hide the bug by making the worker the owner.
    """
    store = _store(tmp_path)
    store.record_trigger(1000.0, 600.0)

    raised: list[BaseException] = []

    def from_another_thread() -> None:
        try:
            store.record_trigger(1100.0, 600.0)
            store.record_attempt(1100.0, 0, Tier.TIER_1)
            store.settle_pending(1200.0, PARAMS)
        except BaseException as exc:  # noqa: BLE001 - the point is to report it
            raised.append(exc)

    worker = threading.Thread(target=from_another_thread)
    worker.start()
    worker.join(timeout=5.0)

    assert not worker.is_alive()
    assert raised == []
    assert store.repeat_count(1200.0, 600.0, "") == 2
    store.close()


def test_concurrent_settles_do_not_lose_an_update(tmp_path):
    """check_same_thread=False alone would make this fail quietly, not loudly.

    settle_pending() reads an action value, computes the next one from it
    and writes it back. Interleave two of those and one event's learning
    vanishes with no error raised anywhere - which is why the lock, not
    just the connection flag, is what makes this class safe.

    Asserted on visits rather than value: visits is an exact integer count
    of how many settles were applied, so a lost update is unambiguous,
    where a value comparison would depend on the interleaving order.
    """
    store = _store(tmp_path)
    attempts = 8
    for i in range(attempts):
        store.record_attempt(1000.0 + i, 0, Tier.TIER_1)

    start = threading.Barrier(attempts)

    def settle_one() -> None:
        start.wait(timeout=5.0)
        store.settle_pending(2000.0, PARAMS)

    workers = [threading.Thread(target=settle_one) for _ in range(attempts)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5.0)

    assert not any(worker.is_alive() for worker in workers)
    assert store.action_values()[(0, Tier.TIER_1)] is not None
    connection = sqlite3.connect(str(store.db_path))
    try:
        visits = connection.execute(
            "SELECT visits FROM action_values WHERE species = '' AND context = 0 AND tier = ?",
            (int(Tier.TIER_1),),
        ).fetchone()[0]
        unsettled = connection.execute(
            "SELECT COUNT(*) FROM attempts WHERE settled = 0"
        ).fetchone()[0]
    finally:
        connection.close()

    assert visits == attempts
    assert unsettled == 0
    store.close()
