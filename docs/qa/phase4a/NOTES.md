# Phase 4a — Overview screen QA notes

## Automated screenshots

Captured via `scripts/qa-phase4a-screenshots.mjs` against a locally seeded dataset
(`overview_sample.sql`, 7 nodes / 6 health rows / 4 events, one with `vision`
dropped out on the fused decision).

- `overview-desktop.png` / `overview-mobile.png` — default state.
- `overview-node-desktop.png` / `overview-node-mobile.png` — node S7-06 selected,
  digital-twin panel open.

Compared against `docs/design-reference/SectorMap.dc.html` and
`EleTect Platform.dc.html` (lines 745-836): dark CARTO basemap, status pin colors
(green/yellow/red/grey) and the alert ping ring all match. The static mockup's
on-map legend and "N ↑ · 1 km" scale label are superseded by the live
`FleetSummaryTiles` counts above the map (same colors, real numbers) rather than
duplicated on the map itself — a deliberate adaptation for an interactive map vs.
a static illustration, not a fidelity gap.

The dropped-out sensor case renders correctly: S7-06's boar event shows
"Vision — unavailable · dropped out" rather than a fabricated 0%, and the
confidence radar collapses that axis to the centroid instead of plotting a false
point.

## Realtime verification — manual, not automated

An automated polling script (`realtime-check.mjs`, not committed) was used to try
to catch a `nodes.status` update via the live `postgres_changes` subscription.
Across three windows (20s, 90s, 120s — about 4 minutes total) it never detected
the flip, despite the update having actually been run. The script's detection
logic (`text=ALERT` locator → parent `innerText` → string split) was fragile
against the real tile DOM structure; this was a detection-script bug, not a
realtime-feature bug. The script was discarded rather than fixed, since a direct
manual check is stronger evidence anyway.

Manual verification (run by the project owner, screen-observed, not scripted):
logged in as `officer@eletect.in`, ran

```sql
update nodes set status='alert' where id='S7-08';
```

in the Supabase SQL editor while the Overview screen was open in another window.
Observed, side by side, with no page refresh:

- Fleet tiles went from `3 Healthy / 2 Attention / 1 Alert / 1 Offline` to
  `2 Healthy / 2 Attention / 2 Alert / 1 Offline` the instant the SQL editor
  reported "Success. No rows returned."
- The S7-08 pin on the live map turned from green to red and picked up the
  `et-ping` animated ring, matching the alert-state styling used for S7-05.

This confirms the `useRealtimeTable` subscription (`postgres_changes` on
`nodes`, already in the `supabase_realtime` publication) delivers UPDATEs to the
Overview screen live, with both the map marker and the derived fleet-summary
counts reacting correctly. Screenshots of this manual run were shared in chat
but not saved to disk, so they are not checked in — this note stands in as the
verification record.
