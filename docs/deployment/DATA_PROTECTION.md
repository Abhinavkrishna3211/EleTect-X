# Personal data, retention and erasure

Scope: the EleTect X web backend, the ranger dashboard and the field nodes, as they stand on
2 October 2026. Written against India's Digital Personal Data Protection Act, 2023.

This is a statement of what the system actually holds today and what it does not yet do about it.
Four of the duties below are unmet in code. They are listed as unmet rather than planned, because a
retention policy that exists only in a document is the same as no retention policy.

## Roles

The deploying forest division is the **Data Fiduciary**: it decides why residents' and officers'
contact details are collected and it is answerable for them. This repository is the system the
Fiduciary operates. Three **Data Processors** sit underneath it, each holding personal data on the
Fiduciary's behalf: Supabase (database, auth, edge functions), Resend (email delivery, and
therefore every recipient address and message body), and whoever hosts the ChirpStack instance the
nodes uplink through. A written processing agreement with each is the Fiduciary's to obtain; none
is in this repository.

## What personal data exists, and where

| Data | Where | Why it is held |
|---|---|---|
| Email address | `auth.users.email` | account identity; the only live alert channel |
| Name, phone | `profiles.full_name`, `profiles.phone` | addressing an officer; a second channel once SMS is unblocked |
| Home coordinates | `profiles.lat`, `profiles.lng` | the 3 km proximity filter in `send-alert` |
| Alert opt-in | `profiles.alerts_enabled` | the consent flag itself |
| Role | `profiles.role` | access control |
| Name, department, designation, official email, phone | `officer_requests` | verifying an officer applicant before granting staff access |
| Recipient address, channel, status, timestamp | `alerts` | proof an alert was attempted, per recipient, per event |
| Which officer acknowledged which event, and when | `events.acked_by`, `events.acked_at` | accountability for a critical response |

Two things are **not** personal data today and should stay that way deliberately rather than by
accident:

- **`events.media_url` never holds real imagery.** The only value ever written is the literal
  `'demo'`. Camera frames and encounter clips stay on the node and leave it on a site visit. The
  moment any upload path is added, imagery of a village approach becomes personal data of every
  bystander who walks through frame, and this document needs a section it does not currently need.
- **`public_area_risk`** is the resident-facing view, and migration 0009B filters poaching species
  out of it, so a resident cannot infer where a gunshot was detected. That filter is a privacy
  control; do not widen the view without replacing it.

## Lawful basis and notice

Residents opt in by holding an account and setting `alerts_enabled`; `useAlertsOptIn` is the single
write, and the signup plus email-confirmation flow is the consent record. Officers supply their
details to apply for access.

**Unmet duty 1 — there is no notice.** DPDP s.5 requires an itemised notice, at or before the point
of collection, saying what is collected, for what purpose, how to withdraw consent, how to complain
to the Data Protection Board, and how to exercise rights. The signup form presents none of this.
Consent collected without that notice is not valid consent. This has to be in place before
residents sign up with real contact information.

## Retention — what the system does now

**Nothing expires.** There is no scheduled deletion anywhere in the backend: no `pg_cron` job, no
TTL, no archival. `reset_demo()` and the seed scripts delete their own synthetic rows and nothing
else. Every row listed in the table above is kept indefinitely, including `alerts`, which grows one
row per recipient per alert and carries the address each was sent to.

**Unmet duty 2 — storage limitation.** DPDP s.8(7) requires erasure once the purpose is served and
consent is withdrawn or presumed no longer given. "Until the project ends" is not a retention
period.

The schedule below is the proposal; it is not implemented:

| Data | Keep | Then |
|---|---|---|
| `alerts` rows | 12 months | delete; the operational question "did the alert go out" is answered within days, and the annual report is the only reason to hold them longer |
| `events` and their fusion/corridor/uplink detail | indefinite | retain — no personal data, as long as `media_url` stays non-personal, and the conflict record is the scientific point of the deployment |
| `events.acked_by` / `acked_at` | 24 months | null the pair, keep the event |
| `officer_requests` for rejected applicants | 6 months | delete; held only to stop an immediate re-application |
| `officer_requests` for approved applicants | duration of posting | delete on deactivation |
| A resident account inactive, or opted out, for 24 months | — | delete the profile and the auth user |
| Node-side frames, clips and seismic records | per the caps already in `services/config.py` and ADR 0035 | evicted by size, not by age — add an age cap |

## Erasure and the other rights

**Unmet duty 3 — a resident cannot delete their own account.** `DELETE` on `profiles` is revoked
from `authenticated` (`schema.sql:250`, migration 0007), which is correct as a security control —
self-deletion was an escalation route — but it leaves no erasure path at all. DPDP s.12(3) gives
the Data Principal a right to erasure. An admin-executed deletion, plus a `SECURITY DEFINER`
self-erasure function that removes the profile and the auth user together, is the fix; the cascade
from `auth.users` already destroys the dependent rows.

Correction and access are partly met: a resident can read and update their own `full_name`,
`phone`, `lat`, `lng` and `alerts_enabled` (migration 0008's column grant), which covers correction
for the fields they can see. There is no export of everything held about them.

**Unmet duty 4 — no grievance contact and no Consent Manager.** DPDP s.13 requires a readily
available means of grievance redressal, and s.5(2) requires the notice to name it. Publish a
contact on the dashboard and in the notice.

## Security safeguards

What holds today, and is tested: row-level security on every table; a column-scoped `UPDATE` grant
so a resident cannot change their own role; an approval guard so approving an officer request
cannot promote an existing admin; the deactivated-recipient skip in both fan-out paths, so a
revoked account stops receiving alerts and stops appearing in audit rows; and the poaching filter
on the resident-facing view.

Two gaps worth naming here, because they bear on personal data rather than on function:

- Alert email bodies pass through Resend and are retained in that account's logs. Officer and
  resident addresses are therefore held by a third party, outside this system's own controls.
- Transactional email is still on Supabase's default sender at two messages per hour. Residents who
  sign up will not receive confirmation, which means accounts created and never confirmed — rows of
  contact data held for a purpose that was never fulfilled.

## Breach

DPDP s.8(6) requires notification to the Data Protection Board and to each affected Data Principal,
without the materiality threshold other regimes allow. There is no incident procedure in this
repository. At minimum the Fiduciary needs a named responder, a way to establish which rows were
exposed and over what window, and a template notice. The `alerts` table is the useful artifact for
the second of those.

## Before residents sign up with real contact details

In order:

1. Write and publish the s.5 notice; put it in front of the signup form.
2. Publish a grievance contact.
3. Ship the self-erasure function.
4. Implement the retention schedule as scheduled deletions, not as a document.

Items 1 and 2 are prose, and both are blocking. Item 3 is one `SECURITY DEFINER` function. Item 4
is a `pg_cron` job per row in the table above.
