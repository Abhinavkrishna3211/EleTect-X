// EleTect X — alert wording and audience. Offline. Run from web/backend/functions/send-alert:
//   deno test message.test.ts

import { assertEquals, assertStringIncludes } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { alertText, audienceFor, isPaging } from "./message.ts";

Deno.test("audience: wildlife reaches residents, poaching sounds reach staff only", () => {
  assertEquals(audienceFor({ species: "elephant" }), "staff_and_residents");
  assertEquals(audienceFor({ species: "boar" }), "staff_and_residents");
  assertEquals(audienceFor({ species: null }), "staff_and_residents");
  assertEquals(audienceFor({ species: "gunshot" }), "staff_only");
  assertEquals(audienceFor({ species: "chainsaw" }), "staff_only");
});

Deno.test("text: names the species the node reported", () => {
  const { subject, body } = alertText({ species: "elephant", confidence: 0.87 }, "S7-06");
  assertEquals(subject, "EleTect X alert — S7-06");
  assertEquals(body, "EleTect X: elephant detected near S7-06 (87% confidence). Stay alert, avoid the area.");
  assertStringIncludes(alertText({ species: "boar", confidence: 0.5 }, "x").body, "wild boar detected");
});

Deno.test("text: no species is never guessed", () => {
  assertStringIncludes(alertText({ species: null, confidence: 0.9 }, "x").body, "wildlife confirmed on camera");
  assertStringIncludes(alertText({ species: "leopard", confidence: 0.9 }, "x").body, "wildlife confirmed on camera");
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
