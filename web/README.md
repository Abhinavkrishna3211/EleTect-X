# Web — Monitoring Web App (off-device, not the control loop)

The Forest-Department web application. `frontend/` React PWA (dashboard + marketing); `backend/` Supabase (schema, RLS, functions); `ingest/` ChirpStack MQTT → Supabase. Renamed from 'cloud' to avoid implying on-device control — the node is fully autonomous; this only monitors/alerts.
