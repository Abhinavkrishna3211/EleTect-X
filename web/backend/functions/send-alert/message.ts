// EleTect X — what an alert says and who it goes to, decided from the event row alone.
// Pure (no client, no env) so message.test.ts can pin it down offline.
//
// Two audiences:
//   - wildlife (elephant, boar, or a camera-confirmed target on a multi-species node): officers
//     plus opted-in residents near the node — residents are the people the warning protects;
//   - poaching sounds (gunshot, chainsaw): officers only. Paging a village about a gunshot puts
//     residents on the path towards armed people and tips off whoever fired (ADR 0031).

export type Audience = "staff_and_residents" | "staff_only";

const POACHING = new Set(["gunshot", "chainsaw"]);

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
  return POACHING.has(ev.species ?? "") ? "staff_only" : "staff_and_residents";
}

export function alertText(ev: AlertEvent, place: string): { subject: string; body: string } {
  // No species means the node's camera confirmed one of several targets it deters, without
  // saying which (ADR 0031) — say what is known rather than guess an animal.
  const what = WHAT[ev.species ?? ""] ?? "wildlife confirmed on camera";
  const pct = `${Math.round((ev.confidence ?? 0) * 100)}% confidence`;
  const advice = audienceFor(ev) === "staff_only"
    ? "Respond per anti-poaching protocol."
    : "Stay alert, avoid the area.";
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
