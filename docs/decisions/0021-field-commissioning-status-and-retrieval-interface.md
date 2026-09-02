# ADR 0021: On-demand field commissioning, status, and footage-retrieval interface

- **Status:** proposed
- **Date:** 2026-09-02

## Context

Real, currently-unserved field need: someone (DFO install team, likely not a software engineer) needs
to stand at a deployed node with a phone or laptop, confirm the system actually came up correctly after
install, change a small set of safe config values (`NODE_HOUSEHOLD_PROXIMITY` chief among them), and pull
confirmed event videos off the board — all without SSH/CLI expertise. Today's only path is SSH/SCP with
the right credentials and IP, which does not serve a non-technical field visit. This is a real gap, not
scope creep — a forest boundary node with no way for its own install team to verify it's working is a
real operational risk independent of anything else in this project.

**This depends on ADR 0020 existing first** — there's nothing to list/download until confirmed event
videos exist on the board. Sequenced after, not parallel.

**Real hardware finding from research this pass, needs on-device confirmation before this is built:**
The board's Wi-Fi module (WCBN3536A, Wi-Fi 5 dual-band) is a standard class of module for which AP mode
via `hostapd` is common — but AP-mode support for this specific module/driver combination was not
independently confirmed. **Real check needed first**: `iw list` on the board, looking for `AP` in
supported interface modes.

**Corrected, same day — the original physical-trigger idea doesn't survive contact with the real
enclosure.** A first draft of this ADR proposed a physical button (JBTN1's short press, or the
`VOL_DOWN`/`VOL_UP` GPIO on the JCTL header) as the on-demand activation trigger. **User caught the real
problem: once the board is sealed inside its field enclosure, no internal button is reachable without
opening it** — and opening a weatherproof enclosure routinely for a "quick status check" defeats the
point of a low-friction field tool and risks the seal/IP rating. Corrected in Decision A below.

**The power architecture tension is the same one ADR 0020 already worked through for video, and needs
the same answer.** An access point means the Wi-Fi radio and the MPU are both actively running, not in
the ~0.42-0.45W deep-suspend state ADR 0008 sized the 10-day solar/battery budget around. **Qualified
2 Sept:** that state is not implemented and the figure is third-party — see ADR 0008's 2 Sept addendum.
As with ADR 0020, a higher real baseline makes the always-on alternative worse, so the on-demand design
below stands on stronger ground, not weaker. This cannot run
continuously - it has to be genuinely on-demand, triggered by a deliberate physical action during a field
visit, and time out back to normal operation on its own.

**Safety boundary, stated as a hard requirement, not a preference**: this interface must never be able to
fire an actuator or trigger a reflash, under any framing. The entire discipline this project has held to
- physical presence required for every actuator fire and every reflash - exists specifically so no remote
or semi-remote interface can accidentally become a way around that. A field-commissioning tool that can
view status, toggle safe bounded config, and download files is genuinely useful and genuinely safe; one
that can fire the horn or push firmware is a different, much riskier thing this ADR explicitly does not
propose.

## Decision

**A. On-demand activation via a magnetic reed switch, not an internal button — the enclosure is sealed
in the field and an internal button is unreachable without opening it.** A reed switch mounted just
inside the enclosure wall, wired to a GPIO interrupt, triggers when a technician holds a magnet against
the *outside* of the enclosure at a marked spot — no penetration, no seal broken, genuinely on-demand
(not a scheduled guess). Real, small BOM/assembly addition (reed switch + a magnet for the field kit),
not zero-cost, flagged plainly rather than hidden in "just wire it up." Activation brings up the Wi-Fi AP
and starts the local web server; both shut down automatically after a fixed inactivity timeout (a few
minutes with no requests), returning the MPU to its normal wake/suspend behavior — never left running
past a field visit.

**Alternative if a new part doesn't fit the timeline: a scheduled short AP window** (e.g. 5 minutes once
per boot, or once daily at a predictable time) instead of a reed-switch trigger — zero new hardware, but
burns a small amount of power every single day of the 10 regardless of whether anyone visits, for a
benefit used at most once or twice across the whole trial. Real tradeoff, not a clearly-better fallback —
user's call between the two, not decided here.

**B. Local-only Wi-Fi access point, no internet dependency.** The node creates its own AP with a set
password (not a shared/guessable default) - a phone or laptop joins it directly on-site, no existing
network infrastructure needed at a forest boundary.

**C. A minimal local web page, three sections, explicitly scoped:**
- **Status (read-only)**: boot_id, uptime, free storage, watchdog-armed state, container/service health,
  count of confirmed events since install. The "did this actually work" check.
- **Config (safe, bounded fields only)**: `NODE_HOUSEHOLD_PROXIMITY` toggle, gain/threshold values that
  already exist and are already clamped elsewhere in firmware - this page can only set values inside
  ranges the MCU/MPU already enforce, never introduce a new unclamped path. **No actuator-fire control,
  no reflash trigger, full stop** - this is the one hard line for this ADR.
- **Footage**: list of confirmed videos (from ADR 0020's permanent capture directory) with direct
  download links over the local AP connection.

**D. App-level password on the page itself, separate from the AP password.** Two independent factors -
mostly against an accidental config change by someone who joined the AP without meaning to touch
anything, not a serious threat-model exercise for a device sitting in a forest.

**E. Lightweight implementation, matching this project's existing "simplicity over complexity" bar**:
Python's own `http.server`/a minimal Flask app, not a framework-heavy stack: `hostapd` + `dnsmasq` for
the AP + DHCP, both already standard Debian packages. No new heavy dependency for a tool that exists to
be simple and reliable during a brief field visit.

## Alternatives considered

- **Always-on Wi-Fi AP.** Rejected - same power-budget conflict ADR 0020 already ruled out for the video
  pre-buffer, for the same reason: several watts sustained instead of suspend-level draw, for 10
  unattended field days, in exchange for a convenience only needed during actual field visits.
- **SSH/SCP only, no new interface.** Rejected as the sole answer - real, doesn't serve a non-technical
  field visit, which is the actual gap this ADR addresses. Kept as the fallback/backup access method
  regardless of whether this ships.
- **A phone-hotspot-joins-the-board model instead of the board hosting its own AP.** Rejected as the
  primary design - depends on whoever visits happening to expose a hotspot correctly and the board
  successfully joining it, an extra failure mode; the board hosting its own AP is more robust and doesn't
  depend on visitor phone configuration.

## Consequences

+ Real, serves a genuine field-operations gap - a non-technical install/check visit becomes possible
  without SSH access or credentials memorized/shared insecurely.
+ Footage retrieval becomes trivial for a field visit (browser download) instead of requiring SCP.
+ No new always-on power draw - on-demand activation with an auto-timeout keeps this inside the existing
  wake/suspend power architecture.
- Two real hardware facts are still unconfirmed and block starting implementation: Wi-Fi AP-mode support
  on this module, and which physical button/GPIO is actually free and wired on the on-hand board. Both
  are cheap, fast checks - not done yet.
- Depends on ADR 0020 (video pipeline) shipping first; sequenced work, not parallel.
- This is real, additional scope on top of an already-full week - honestly a "big work" item as flagged,
  worth sequencing deliberately rather than squeezing in alongside everything else already in flight.
