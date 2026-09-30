"""Contract checks between the species registry and the wire format.

A species exists in four places: services/config.py's SPECIES_REGISTRY,
the MCU's uplink_event_class enum, comms/lora_uplink.py's EventClass, and
web/ingest/src/payload.ts's EVENT_CLASS_SPECIES. The registry is the one
that decides policy; the other three carry the byte format and are
hand-written against each other, so nothing at runtime ever compares them.

That is how the previous class-scheme defect happened, and it is why
test_rpc_contract.py already reads schema.md the same way. These tests are
the comparison: a species added to the registry without a wire code, or a
wire code renumbered on one side only, fails here rather than in the field
as a detection the server cannot name.
"""

import re
from pathlib import Path

import pytest

from comms.lora_uplink import EventClass
from services import config

DEVICE_DIR = Path(__file__).resolve().parent.parent.parent
REPO_ROOT = DEVICE_DIR.parent
MCU_UPLINK_PATH = DEVICE_DIR / "mcu" / "src" / "uplink.h"
PAYLOAD_TS_PATH = REPO_ROOT / "web" / "ingest" / "src" / "payload.ts"

# Audiences the routing table in the plan's D7 actually distinguishes.
# "dashboard_only" is the default and the safe one: a species nobody has
# decided to page about shows up in the feed and wakes no phones.
KNOWN_AUDIENCES = frozenset({"residents", "staff_only", "dashboard_only"})


def _mcu_event_classes() -> dict[str, int]:
    """Parse `kName = N,` out of uplink.h's uplink_event_class enum."""
    text = MCU_UPLINK_PATH.read_text(encoding="utf-8")
    body = re.search(
        r"enum class uplink_event_class\s*:\s*uint8_t\s*\{(.*?)\}", text, re.S
    )
    assert body, f"Could not find the uplink_event_class enum in {MCU_UPLINK_PATH}"
    return {name: int(value) for name, value in re.findall(r"(k\w+)\s*=\s*(\d+)", body.group(1))}


def _payload_ts_classes() -> dict[int, str | None]:
    """Parse EVENT_CLASS_SPECIES out of web/ingest/src/payload.ts."""
    text = PAYLOAD_TS_PATH.read_text(encoding="utf-8")
    body = re.search(r"EVENT_CLASS_SPECIES:\s*Record<number,[^>]*>\s*=\s*\{(.*?)\}", text, re.S)
    assert body, f"Could not find EVENT_CLASS_SPECIES in {PAYLOAD_TS_PATH}"
    out: dict[int, str | None] = {}
    for code, value in re.findall(r"(\d+)\s*:\s*(null|'[^']*')", body.group(1)):
        out[int(code)] = None if value == "null" else value.strip("'")
    return out


def test_deterrable_labels_are_exactly_the_registry_keys():
    """DETERRABLE_LABELS must stay derived, not a second hand-kept list.

    It is the safety bound every scope string is validated against. If it
    ever drifts from the registry, a species could be deterrable without
    having a wire code, an audience or a bandit partition decided for it.
    """
    assert config.DETERRABLE_LABELS == tuple(config.SPECIES_REGISTRY)


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_each_species_is_keyed_by_its_own_label(label):
    """The dict key and the entry's own label must agree.

    They are built from the same attribute today; this fails if someone
    later writes the table out by hand and transposes two rows.
    """
    assert config.SPECIES_REGISTRY[label].label == label


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_every_alias_target_is_itself_a_registered_species(label):
    """bandit_policy and deterrence_content must name real registry entries.

    An alias to a label that does not exist would send the bandit looking
    for an action-value partition nobody writes to, and resolve_tier_action
    looking for horn content that was never defined.
    """
    species = config.SPECIES_REGISTRY[label]
    assert species.bandit_policy in config.SPECIES_REGISTRY
    assert species.deterrence_content in config.SPECIES_REGISTRY


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_alias_targets_are_not_themselves_aliases(label):
    """Aliasing is one hop deep, never a chain.

    Fox -> Boar is a lookup. Fox -> Boar -> Elephant would mean the content
    a species fires depends on a row it does not mention, which is exactly
    the indirection this registry exists to remove.
    """
    species = config.SPECIES_REGISTRY[label]
    content_target = config.SPECIES_REGISTRY[species.deterrence_content]
    assert content_target.deterrence_content == content_target.label
    policy_target = config.SPECIES_REGISTRY[species.bandit_policy]
    assert policy_target.bandit_policy == policy_target.label


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_every_audience_is_one_the_backend_knows(label):
    """Audiences stay a closed vocabulary.

    The device never reads this column - the fan-out happens in
    web/backend - so a typo here would otherwise sit unnoticed until it
    reached the routing change that consumes it.
    """
    assert config.SPECIES_REGISTRY[label].alert_audience in KNOWN_AUDIENCES


def test_wire_codes_are_unique():
    """Two species sharing a code would be indistinguishable on the wire."""
    codes = [species.event_class for species in config.SPECIES_REGISTRY.values()]
    assert len(codes) == len(set(codes)), f"duplicate event_class values in {codes}"


def test_no_species_claims_the_unconfirmed_code():
    """0 means "the camera did not confirm a species" and must stay free.

    A species mapped to 0 would report every confirmed sighting as an
    unnamed seismic alert.
    """
    assert 0 not in {species.event_class for species in config.SPECIES_REGISTRY.values()}


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_registry_wire_code_matches_the_python_enum(label):
    """SPECIES_REGISTRY's int and EventClass's member must be the same code.

    comms/lora_uplink.py already calls EventClass() on this value at
    import, so a mismatch is a hard failure there too - this names which
    species is wrong instead of raising a bare ValueError on a module load.
    """
    code = config.SPECIES_REGISTRY[label].event_class
    assert EventClass(code).name == label.upper(), (
        f"{label} is wire code {code}, which EventClass calls "
        f"{EventClass(code).name}. Append-only: check whether a code was "
        "renumbered on one side."
    )


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_registry_wire_code_matches_the_mcu_enum(label):
    """device/mcu/src/uplink.h must carry the same code for the same species.

    The MCU is what actually writes the byte. If it disagrees with the
    registry, the species the node believes it reported is not the one the
    server decodes.
    """
    mcu = _mcu_event_classes()
    key = f"k{label}"
    assert key in mcu, (
        f"{MCU_UPLINK_PATH.name} has no {key}. A new species needs its "
        "wire code appended there, in comms/lora_uplink.py and in "
        "web/ingest/src/payload.ts, in lockstep - codes are never renumbered."
    )
    assert mcu[key] == config.SPECIES_REGISTRY[label].event_class


def test_mcu_class_max_covers_every_registered_species():
    """UPLINK_EVENT_CLASS_MAX gates what the MCU will send.

    A code above it is flattened to kUnconfirmed, so a species can be fully
    wired on both sides and still never reach the server if this was not
    bumped with it.
    """
    text = MCU_UPLINK_PATH.read_text(encoding="utf-8")
    match = re.search(r"#define\s+UPLINK_EVENT_CLASS_MAX\s+(\d+)", text)
    assert match, f"Could not find UPLINK_EVENT_CLASS_MAX in {MCU_UPLINK_PATH}"
    highest = max(species.event_class for species in config.SPECIES_REGISTRY.values())
    assert int(match.group(1)) >= highest


@pytest.mark.parametrize("label", sorted(config.SPECIES_REGISTRY))
def test_registry_wire_code_matches_the_cloud_decoder(label):
    """web/ingest must decode the code to this species' name, lowercased.

    This is the end of the chain: whatever the node sends, EVENT_CLASS_SPECIES
    is what turns it into the string a ranger reads on the dashboard. The
    lowercase rule is the existing convention in payload.ts, not a new one.
    """
    cloud = _payload_ts_classes()
    code = config.SPECIES_REGISTRY[label].event_class
    assert code in cloud, (
        f"web/ingest/src/payload.ts does not decode event class {code} "
        f"({label}). Every registered species needs an entry there or its "
        "detections arrive with no species at all."
    )
    assert cloud[code] == label.lower()


def test_the_cloud_decoder_reserves_zero_for_no_species():
    """Code 0 must decode to null on both sides, not to a species name."""
    assert _payload_ts_classes().get(0, "missing") is None
