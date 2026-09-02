"""Tests for perception/storage.py's event-video lifecycle (ADR 0020).

Everything here runs on a tmp_path, never on services.config.CAPTURE_DIR:
each function under test takes its directory as an argument precisely so
the real capture directory is never a test's working surface.

The recurring assertion in this file is a negative one - that a function
returns or logs rather than raising. That is deliberate and it is the
module's actual contract: by the time any of this runs, the deterrents
have already fired and the camera is already closed, so a storage fault
must not be allowed to take down the handler for the *next* event. The
sole exception is scratch_video_path(), which does raise, because a caller
with no scratch path has nothing to record to.
"""

import os
import sys

import pytest

from perception.storage import (
    CaptureEventTag,
    clear_orphaned_scratch,
    commit_video,
    discard_video,
    scratch_video_path,
)

TAG = CaptureEventTag(
    event_timestamp_s=1725000000.5,
    sta_lta_ratio=6.25,
    fused_probability=0.812,
    alert=True,
)


def _write(path, data=b"fake matroska bytes"):
    """Create a stand-in for a finished recording."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# ---------------------------------------------------------------------------
# scratch_video_path
# ---------------------------------------------------------------------------


def test_scratch_path_creates_the_directory_and_does_not_exist_yet(tmp_path):
    """The reserved path must be free, and its parent must be ready to write into.

    perception/video.py hands this straight to a GStreamer filesink, which
    creates the file but not the directory above it.
    """
    scratch = tmp_path / "nested" / ".scratch"
    path = scratch_video_path(scratch, ".mkv")
    assert scratch.is_dir()
    assert path.parent == scratch
    assert not path.exists()
    assert path.suffix == ".mkv"


def test_successive_scratch_paths_are_distinct(tmp_path):
    """Two overlapping events must never be handed the same file to record into.

    The loop is synchronous today, so this cannot happen yet - but the name
    is built from a monotonic counter specifically so it stays true if a
    second handler ever runs concurrently, and a resolution collapse (a
    coarse clock, a truncated counter) would be silent otherwise.
    """
    paths = {scratch_video_path(tmp_path, ".mkv") for _ in range(20)}
    assert len(paths) == 20


def test_scratch_path_raises_when_the_directory_cannot_be_created(tmp_path):
    """The one function here that is allowed to raise, and must.

    A caller that cannot reserve a scratch path has nowhere to record, and
    should learn that here rather than at the first encoder write - by
    which point the pipeline is already running and the event is underway.
    Provoked by putting a regular file where the directory needs to be.
    """
    blocker = tmp_path / "blocked"
    blocker.write_bytes(b"")
    with pytest.raises(OSError):
        scratch_video_path(blocker / "scratch", ".mkv")


# ---------------------------------------------------------------------------
# commit_video
# ---------------------------------------------------------------------------


def test_commit_moves_the_recording_and_names_it_from_the_tag(tmp_path):
    """A committed clip must carry the same event-derived name a JPEG burst does.

    Same _event_prefix as save_burst, so a clip and the burst from the same
    event sort next to each other in the capture directory - which is how
    anyone reviewing evidence in the field will actually find them.
    """
    scratch = _write(tmp_path / "scratch" / "event_1.mkv")
    out_dir = tmp_path / "captures"

    committed = commit_video(scratch, TAG, out_dir)

    assert committed is not None
    assert not scratch.exists()
    assert committed.parent == out_dir
    assert committed.suffix == ".mkv"
    assert committed.read_bytes() == b"fake matroska bytes"
    assert "sta6.25" in committed.name
    assert "p0.812" in committed.name
    assert committed.name.endswith("_alert1.mkv")


def test_commit_records_alert0_for_a_confirmed_but_unalerted_event(tmp_path):
    """The keep-gate half that save_burst never produces.

    A JPEG burst is only ever saved on the alert path, so every burst
    filename ends _alert1. A video committed because vision confirmed an
    elephant that fusion did not clear the threshold for is a real,
    expected case that ends _alert0 - and anyone grepping the capture
    directory needs that to be a documented outcome, not a bug report.
    """
    scratch = _write(tmp_path / "scratch" / "event_1.mkv")
    tag = CaptureEventTag(
        event_timestamp_s=1725000000.5,
        sta_lta_ratio=2.0,
        fused_probability=0.41,
        alert=False,
    )

    committed = commit_video(scratch, tag, tmp_path / "captures")

    assert committed is not None
    assert committed.name.endswith("_alert0.mkv")


def test_commit_creates_the_capture_dir_when_it_is_missing(tmp_path):
    """First event on a fresh install must not lose its clip to a missing dir."""
    scratch = _write(tmp_path / "scratch" / "event_1.mkv")
    out_dir = tmp_path / "not" / "created" / "yet"

    committed = commit_video(scratch, TAG, out_dir)

    assert committed is not None and committed.exists()


def test_commit_of_a_missing_scratch_file_returns_none_without_raising(tmp_path):
    """A crash or an earlier discard must not turn into an exception here.

    The caller (services/reflex_loop.py) reaches this after the horn has
    fired; there is nothing left to salvage by raising.
    """
    assert commit_video(tmp_path / "gone.mkv", TAG, tmp_path / "captures") is None


def test_commit_discards_a_zero_byte_recording_instead_of_committing_it(tmp_path):
    """An empty container is not footage, and must not be filed as if it were.

    A pipeline that produced no encoded bytes leaves a file no player can
    open. Committing it would make the event look captured when it was not
    - worse than having nothing, because it hides the failure. Removing it
    is not an ADR 0020 Decision C deletion: nothing was captured to keep.
    """
    scratch = _write(tmp_path / "scratch" / "event_1.mkv", b"")
    out_dir = tmp_path / "captures"

    assert commit_video(scratch, TAG, out_dir) is None
    assert not scratch.exists()
    assert not out_dir.exists() or list(out_dir.iterdir()) == []


def test_a_failed_commit_reports_none_and_leaves_the_recording_in_scratch(tmp_path):
    """A failed os.replace must report None, never a path to a file that isn't there.

    Modelled by occupying the exact destination name with a directory,
    which os.replace cannot overwrite with a file on any supported
    platform. The point is the contract, not the errno: the scratch file
    survives so the next run's cleanup can at least account for it, and
    the caller learns the commit did not happen.
    """
    scratch = _write(tmp_path / "scratch" / "event_1.mkv")
    out_dir = tmp_path / "captures"
    out_dir.mkdir()
    (out_dir / f"{TAG.event_timestamp_s:.3f}_sta6.25_p0.812_alert1.mkv").mkdir()

    assert commit_video(scratch, TAG, out_dir) is None
    assert scratch.exists()


# ---------------------------------------------------------------------------
# discard_video
# ---------------------------------------------------------------------------


def test_discard_removes_the_scratch_file(tmp_path):
    """The common case: a trigger that turned out not to be an elephant."""
    scratch = _write(tmp_path / "scratch" / "event_1.mkv")
    assert discard_video(scratch) is True
    assert not scratch.exists()


def test_discard_of_a_missing_file_reports_success(tmp_path):
    """Already gone and just removed are the same outcome to the caller.

    Matters because a failed EventVideoRecorder.open() discards its own
    scratch file, and the reflex loop may then discard again at its exit.
    """
    assert discard_video(tmp_path / "never_existed.mkv") is True


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX directory permissions")
def test_discard_reports_failure_without_raising(tmp_path):
    """An undeletable file is logged and reported, never raised.

    Same reasoning as commit: the deterrent sequence is over, and crashing
    the handler would cost the next real event to save one stale file.
    """
    holder = tmp_path / "holder"
    scratch = _write(holder / "event_1.mkv")
    os.chmod(holder, 0o500)
    try:
        assert discard_video(scratch) is False
    finally:
        os.chmod(holder, 0o700)


# ---------------------------------------------------------------------------
# clear_orphaned_scratch
# ---------------------------------------------------------------------------


def test_clear_orphaned_scratch_removes_leftovers_and_counts_them(tmp_path):
    """Startup cleanup after a run that died mid-record.

    On this board the likeliest cause is the documented 5V brown-out. Those
    files are undecided by definition - nothing recorded which event they
    belong to - so there is no tag to commit them under and no way to make
    them useful.
    """
    scratch = tmp_path / ".scratch"
    for name in ("event_1.mkv", "event_2.mkv", "event_3.mkv"):
        _write(scratch / name)

    assert clear_orphaned_scratch(scratch) == 3
    assert list(scratch.iterdir()) == []


def test_clear_orphaned_scratch_on_a_missing_directory_is_zero(tmp_path):
    """A clean first boot and a clean shutdown are the same thing to the caller."""
    assert clear_orphaned_scratch(tmp_path / "never_created") == 0


def test_clear_orphaned_scratch_only_touches_its_own_directory(tmp_path):
    """The guard on ADR 0020 Decision C: committed captures are never deleted.

    The scratch directory is a child of the capture directory (so
    os.replace stays within one filesystem), which puts a recursive or
    parent-walking cleanup one mistake away from wiping the evidence it
    exists to protect. This pins the blast radius.
    """
    captures = tmp_path / "captures"
    scratch = captures / ".scratch"
    keeper = _write(captures / "1725000000.500_sta6.25_p0.812_alert1.mkv")
    sibling = _write(captures / "unrelated.jpg")
    _write(scratch / "event_1.mkv")

    assert clear_orphaned_scratch(scratch) == 1
    assert keeper.exists()
    assert sibling.exists()


def test_clear_orphaned_scratch_leaves_subdirectories_alone(tmp_path):
    """Only files are removed - a directory here is not a recording.

    Anything nested under scratch was put there by something other than
    this project's recorder, and guessing at it is how a cleanup becomes a
    data-loss bug.
    """
    scratch = tmp_path / ".scratch"
    nested = scratch / "somebody_elses"
    _write(nested / "keep.txt")
    _write(scratch / "event_1.mkv")

    assert clear_orphaned_scratch(scratch) == 1
    assert (nested / "keep.txt").exists()
