// EleTect X — what an alert says and who it goes to, decided from the event row alone.
// Pure (no client, no env) so message.test.ts can pin it down offline.
//
// Two audiences:
//   - staff_and_residents: officers plus opted-in residents within 3 km of the node. Residents
//     are the people the warning protects, so this is the right answer for an animal that will
//     walk into a village;
//   - staff_only: officers and nobody else. Poaching sounds are the obvious case — paging a
//     village about a gunshot puts residents on the path towards armed people and tips off
//     whoever fired (ADR 0031) — but it is also the answer for anything this build cannot name.

export type Audience = "staff_and_residents" | "staff_only";

const POACHING = new Set(["gunshot", "chainsaw"]);

// Species -> audience, stated once per species, with no fallthrough.
//
// This map used to be a single negative test: not a poaching sound, therefore residents. That
// fails *open* — every species the map does not know, including a null one and any class a
// newer firmware starts sending, resolves to "wake every phone within 3 km". The one failure
// mode that destroys an alerting system is the alert nobody believes any more, and it is reached
// by over-sending, not under-sending.
//
// So the default is staff_only and each resident-facing species is named deliberately:
//
//   - elephant      a confirmed elephant is the whole reason residents opted in;
//   - elephant_call heard and not seen. It never reaches here today (web/ingest's eventPriority
//                   leaves it 'normal', so send-alert skips it before asking), and it is listed
//                   anyway so that if it ever is promoted, the promotion is a deliberate edit to
//                   this line rather than a silent consequence of a priority change elsewhere;
//   - boar, fox     real detections that belong on the dashboard. Same story: 'normal' today, and
//                   named here so no future priority change can fan them out by accident;
//   - gunshot,
//     chainsaw      officers only, for the reason above.
//
// A null species is deliberately absent. It means the camera confirmed nothing, which the node
// now says explicitly (ADR 0031 as amended by the species-on-the-frame change) — so there is no
// animal to warn residents about and no text that would tell them what to avoid. The one way a
// null-species row can still page is the no-retreat flag, which 'critical' carries independently
// of the class byte; officers are paged for it, and residents are not told a species the node
// could not name.
const AUDIENCE: Record<string, Audience> = {
  elephant: "staff_and_residents",
  elephant_call: "staff_only",
  boar: "staff_only",
  fox: "staff_only",
  gunshot: "staff_only",
  chainsaw: "staff_only",
};

// Priorities that fan out. 'critical' is the no-retreat flag (ADR 0034): the node fired its top
// tier and the animal stayed, so it pages everyone a 'high' would, with a line asking for a team.
// Anything else - 'normal', or a value this build does not know - stays on the dashboard.
const PAGING_PRIORITIES = new Set(["high", "critical"]);

export function isPaging(priority: string | null | undefined): boolean {
  return PAGING_PRIORITIES.has(priority ?? "normal");
}

const WHAT: Record<string, string> = {
  elephant: "elephant detected",
  boar: "wild boar detected",
  gunshot: "possible gunshot heard",
  chainsaw: "chainsaw heard",
  elephant_call: "elephant heard (not seen on camera)",
  fox: "fox detected",
};

export interface AlertEvent {
  species?: string | null;
  confidence?: number | null;
  priority?: string | null;
}

export function audienceFor(ev: AlertEvent): Audience {
  return AUDIENCE[ev.species ?? ""] ?? "staff_only";
}

export function alertText(ev: AlertEvent, place: string): { subject: string; body: string } {
  // Reaching the fallback means one of two things, and neither is a camera confirmation: the
  // row carries no species at all, or it carries a class from firmware newer than this build.
  // The node names what it confirmed (ADR 0031 as amended), so "confirmed on camera" would be
  // asserting something the row does not say — and an officer acting on a wrong certainty is
  // worse served than one told plainly that the species is unknown.
  const what = WHAT[ev.species ?? ""] ?? "unidentified detection";
  const pct = `${Math.round((ev.confidence ?? 0) * 100)}% confidence`;
  // Keyed off the species, not off the audience. Those were the same test while staff_only
  // meant "poaching sound"; now staff_only is also the default for anything unnamed, and
  // telling an officer to follow the anti-poaching protocol because the class byte was one
  // this build does not know would be a fabricated instruction.
  const advice = POACHING.has(ev.species ?? "")
    ? "Respond per anti-poaching protocol."
    : audienceFor(ev) === "staff_and_residents"
      ? "Stay alert, avoid the area."
      : "Officers only — this was not sent to residents.";
  // Residents within 3 km get this same text, so it states that a team is being
  // called rather than telling the reader to send one.
  if (ev.priority === "critical") {
    return {
      subject: `EleTect X URGENT — ${place}`,
      body: `EleTect X URGENT: ${what} near ${place} (${pct}) has not retreated after full deterrence. ` +
        `Forest team requested. ${advice}`,
    };
  }
  return {
    subject: `EleTect X alert — ${place}`,
    body: `EleTect X: ${what} near ${place} (${pct}). ${advice}`,
  };
}
