"""29 Sept model swap: Fox as a scope choice, and the vision-only watch window."""

import importlib

from services import reflex_loop


def _reload_config(monkeypatch, home_test: str, scope: str = "both"):
    monkeypatch.setenv("ELETECT_HOME_TEST_MODE", home_test)
    monkeypatch.setenv("ELETECT_DETERRENCE_SCOPE", scope)
    monkeypatch.delenv("ELETECT_EVENT_VIDEO_SCOPE", raising=False)
    from services import config

    return importlib.reload(config)


def test_the_operating_mode_no_longer_decides_what_is_deterred(monkeypatch):
    """Scope decides, and only scope. HOME_TEST_MODE must not move these lists.

    Fox used to be appended to both target lists whenever HOME_TEST_MODE
    was set, because the 3-class model renamed the backyard trial's
    visitors from "Boar" to "Fox" and no deterrence scope could name them.
    That append ran after the scope had already resolved, so the node
    deterred a species its own configuration did not name and no scope
    string could switch it off. A scope can name Fox now, so the mode flag
    has no business in this decision - and this test fails if it comes
    back.
    """
    try:
        for mode in ("0", "1"):
            cfg = _reload_config(monkeypatch, mode, "both")
            assert cfg.HOME_TEST_MODE is (mode == "1")
            assert "Fox" not in cfg.DETERRENT_TARGET_LABELS
            assert "Fox" not in cfg.EVENT_VIDEO_TARGET_LABELS
    finally:
        monkeypatch.undo()
        from services import config

        importlib.reload(config)


def test_the_backyard_node_deters_foxes_by_naming_them_in_its_scope(monkeypatch):
    """The replacement for the gate: the trial still works, by configuration.

    Checked in home-test mode and outside it, because the whole point is
    that the two are now indistinguishable here - the backyard node and a
    field node commissioned for foxes get the same behaviour from the same
    scope string.
    """
    try:
        for mode in ("0", "1"):
            cfg = _reload_config(monkeypatch, mode, "Elephant,Boar,Fox")
            assert cfg.DETERRENT_TARGET_LABELS == ("Elephant", "Boar", "Fox")
            assert cfg.EVENT_VIDEO_TARGET_LABELS == ("Elephant", "Boar", "Fox")
            # The gate appended Fox after the DB filename was derived, so
            # the extra species learned into the narrower scope's store.
            # Named in the scope, it keys its own.
            assert cfg.EXPERIENCE_DB_PATH.name == "experience-elephant-boar-fox.sqlite3"
    finally:
        monkeypatch.undo()
        from services import config

        importlib.reload(config)


def test_a_vision_only_trigger_gets_the_extended_watch():
    """No geophone at all is not the same as a weak geophone reading."""
    assert reflex_loop._watch_length_s(
        repeat_count=0, seismic_alone_alerts=False, seismic_available=False,
        base_s=8.0, extended_s=45.0,
    ) == 45.0


def test_a_weak_real_geophone_trigger_still_gets_the_base_watch():
    """The field path's cheap window is unchanged."""
    assert reflex_loop._watch_length_s(
        repeat_count=0, seismic_alone_alerts=False, base_s=8.0, extended_s=45.0,
    ) == 8.0


def test_a_confirmed_fox_gets_the_boar_policy():
    """Foxes keep the arms the bandit learned when they were labelled Boar."""
    reading = reflex_loop.ModalityReading(reflex_loop.Modality.VISION, 2.0, available=True)
    check = reflex_loop.VisionCheck(reading, True, species=("Fox",))
    assert reflex_loop._deterrence_species(
        check, target_labels=("Elephant", "Boar", "Fox")
    ) == "Boar"
