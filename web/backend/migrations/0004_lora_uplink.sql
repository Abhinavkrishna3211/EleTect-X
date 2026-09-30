-- 0004 — LoRaWAN event frames (ADR 0031).
--
-- web/ingest now decodes the node's raw uplink bytes itself instead of relying on
-- a ChirpStack payload codec. What the frame says beyond species/confidence -
-- whether the camera confirmed it, the deterrence tier, whether a deterrent
-- fired, safe mode, the frame's seq and the radio metadata - lands in this
-- column. seq is also what ingest checks to drop a frame the node re-sent.
--
-- Additive and nullable: existing rows and the demo scenarios are unaffected.

alter table events add column if not exists uplink jsonb;

comment on column events.uplink is
  'Decoded LoRaWAN event frame (ADR 0031): seq, class, tier, flags and radio '
  'metadata. Null for events that did not arrive over LoRa.';

-- ingest's re-send check reads (node_id, uplink->>seq) over the last few
-- minutes; the existing (node_id, ts desc) index already narrows that to a
-- handful of rows, so no new index.
