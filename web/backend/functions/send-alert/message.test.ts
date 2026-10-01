// EleTect X — alert wording and audience. Offline. Run from web/backend/functions/send-alert:
//   deno test message.test.ts

import { assertEquals, assertStringIncludes } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { alertText, audienceFor, isPaging } from "./message.ts";

Deno.test("audience: a confirmed elephant reaches residents, everything else does not", () => {
  assertEquals(audienceFor({ species: "elephant" }), "staff_and_residents");
  assertEquals(audienceFor({ species: "gunshot" }), "staff_only");
  assertEquals(audienceFor({ species: "chainsaw" }), "staff_only");
  // Dashboard species. They do not page at all today (web/ingest leaves them 'normal'), and
  // they are pinned here so a later priority change cannot fan them out as a side effect.
  assertEquals(audienceFor({ species: "boar" }), "staff_only");
  assertEquals(audienceFor({ species: "fox" }), "staff_only");
  assertEquals(audienceFor({ species: "elephant_call" }), "staff_only");
});

Deno.test("audience: an unmapped species is staff_only, not a village-wide page", () => {
  // The regression this guards is the original implementation: "not a poaching sound, therefore
  // residents". Under it every one of these woke every opted-in phone within 3 km of the node.
  assertEquals(audienceFor({ species: null }), "staff_only");
  assertEquals(audienceFor({ species: undefined }), "staff_only");
  assertEquals(audienceFor({}), "staff_only");
  assertEquals(audienceFor({ species: "" }), "staff_only");
  // A class from firmware newer than this build decodes to a name nothing here knows.
  assertEquals(audienceFor({ species: "leopard" }), "staff_only");
  assertEquals(audienceFor({ species: "ELEPHANT" }), "staff_only");
  // Including at critical, which is the one priority that pages on a null species.
  assertEquals(audienceFor({ species: null, priority: "critical" }), "staff_only");
});

Deno.test("text: names the species the node reported", () => {
  const { subject, body } = alertText({ species: "elephant", confidence: 0.87 }, "S7-06");
  assertEquals(subject, "EleTect X alert — S7-06");
  assertEquals(body, "EleTect X: elephant detected near S7-06 (87% confidence). Stay alert, avoid the area.");
  assertStringIncludes(alertText({ species: "boar", confidence: 0.5 }, "x").body, "wild boar detected");
});

Deno.test("text: no species is never guessed, and never claimed as confirmed", () => {
  // The node names what its camera confirmed, so reaching the fallback means the row named
  // nothing or named a class this build predates. Either way "confirmed on camera" - the old
  // wording - asserted a certainty the row does not carry.
  assertStringIncludes(alertText({ species: null, confidence: 0.9 }, "x").body, "unidentified detection");
  assertStringIncludes(alertText({ species: "leopard", confidence: 0.9 }, "x").body, "unidentified detection");
});

Deno.test("text: the anti-poaching instruction is only given for a poaching sound", () => {
  // advice used to be derived from the audience, which was the same question while staff_only
  // meant "gunshot or chainsaw". It is not any more, and an officer told to follow the
  // anti-poaching protocol because a class byte was unrecognised has been given a fabricated
  // instruction.
  for (const species of [null, "leopard", "boar", "fox", "elephant_call"]) {
    const { body } = alertText({ species, confidence: 0.9, priority: "high" }, "x");
    assertEquals(body.includes("anti-poaching"), false, `${species} must not cite the protocol`);
    assertStringIncludes(body, "not sent to residents");
  }
  assertStringIncludes(
    alertText({ species: "chainsaw", confidence: 0.9 }, "x").body,
    "Respond per anti-poaching protocol.",
  );
  // And the resident-facing species still gets resident-facing advice.
  assertStringIncludes(
    alertText({ species: "elephant", confidence: 0.9 }, "x").body,
    "Stay alert, avoid the area.",
  );
});

Deno.test("text: poaching alerts carry the officer instruction, not resident advice", () => {
  const { body } = alertText({ species: "gunshot", confidence: 0.95 }, "S7-09");
  assertEquals(body, "EleTect X: possible gunshot heard near S7-09 (95% confidence). Respond per anti-poaching protocol.");
});

Deno.test("paging: high and critical fan out, nothing else does", () => {
  assertEquals(isPaging("high"), true);
  assertEquals(isPaging("critical"), true);
  assertEquals(isPaging("normal"), false);
  assertEquals(isPaging(null), false);
  assertEquals(isPaging(undefined), false);
  assertEquals(isPaging("urgent"), false);
});

Deno.test("text: a no-retreat alert asks for a team", () => {
  const { subject, body } = alertText({ species: "elephant", confidence: 0.91, priority: "critical" }, "S7-06");
  assertEquals(subject, "EleTect X URGENT — S7-06");
  assertEquals(
    body,
    "EleTect X URGENT: elephant detected near S7-06 (91% confidence) has not retreated after full deterrence. " +
      "Forest team requested. Stay alert, avoid the area.",
  );
});

Deno.test("text: newer classes are named, an elephant call says it was not seen", () => {
  assertStringIncludes(alertText({ species: "elephant_call", confidence: 0.8 }, "x").body, "not seen on camera");
  assertStringIncludes(alertText({ species: "fox", confidence: 0.8 }, "x").body, "fox detected");
});
