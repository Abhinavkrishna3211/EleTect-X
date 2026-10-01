// EleTect X — fan-out unit tests. No live project, no network: a stub client stands in for
// Supabase. Run from web/backend/functions/send-alert:
//   deno test --no-check --allow-env fanout.test.ts
// (--allow-env: the test forces channels off via env for determinism; --no-check: skip fetching
//  the type-only supabase-js import so the run is fully offline.)

import { assert, assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { fanOut, kmBetween, withinRadius } from "./fanout.ts";

// Minimal stand-in for the two SupabaseClient surfaces fanOut/deliver touch: alerts inserts and
// auth.admin.getUserById. getUserById rejects for `poisonId` to simulate a lookup failure.
function makeStub(poisonId: string) {
  const inserts: { table: string; row: Record<string, unknown> }[] = [];
  const lookups: string[] = [];
  const client = {
    from(table: string) {
      return {
        insert(row: Record<string, unknown>) {
          inserts.push({ table, row });
          return Promise.resolve({ data: null, error: null });
        },
      };
    },
    auth: {
      admin: {
        getUserById(id: string) {
          lookups.push(id);
          if (id === poisonId) return Promise.reject(new Error("simulated getUserById failure"));
          return Promise.resolve({ data: { user: { id, email: `${id}@example.test` } }, error: null });
        },
      },
    },
  };
  return { client, inserts, lookups };
}

Deno.test("fanOut: a getUserById failure skips only that recipient, not the rest of the batch", async () => {
  // Force every channel off so the run is deterministic and never touches the network: each
  // reached recipient then falls through deliver() to a single `undeliverable` audit row.
  Deno.env.set("CHANNEL_EMAIL", "off");
  Deno.env.delete("CHANNEL_SMS");
  Deno.env.delete("CHANNEL_WHATSAPP");

  const before = "11111111-1111-1111-1111-111111111111";
  const poison = "22222222-2222-2222-2222-222222222222";
  const after = "33333333-3333-3333-3333-333333333333";
  const { client, inserts, lookups } = makeStub(poison);

  const people = [
    { id: before, phone: null },
    { id: poison, phone: null },   // lookup throws here
    { id: after, phone: null },
  ];

  const result = await fanOut(
    client as unknown as Parameters<typeof fanOut>[0],
    people,
    { subject: "s", body: "b" },
    42,
  );

  // The failure did not propagate — fanOut resolved rather than throwing.
  // Every recipient was attempted, in order, the poison one included.
  assertEquals(lookups, [before, poison, after]);

  // The recipient AFTER the failure still reached delivery: the batch was not taken out.
  const audited = inserts.filter((i) => i.table === "alerts").map((i) => i.row.recipient).sort();
  assertEquals(audited, [`${before}@example.test`, `${after}@example.test`].sort());

  // The poison recipient produced no audit row at all (skipped, not half-processed).
  assert(!audited.includes(`${poison}@example.test`));
  assert(!audited.includes(poison));

  // Channels all off → every reached recipient is terminal-undeliverable, nothing "sent".
  assertEquals(result.sent, 0);
  assertEquals(result.byChannel, {});
  for (const i of inserts) assertEquals(i.row.status, "undeliverable");
});

Deno.test("fanOut: undeliverable row carries a recipient identifier and null channel", async () => {
  Deno.env.set("CHANNEL_EMAIL", "off");
  const id = "44444444-4444-4444-4444-444444444444";
  const { client, inserts } = makeStub("none");

  await fanOut(
    client as unknown as Parameters<typeof fanOut>[0],
    [{ id, phone: "+919999900000" }],
    { subject: "s", body: "b" },
    7,
  );

  assertEquals(inserts.length, 1);
  const row = inserts[0].row;
  assertEquals(row.status, "undeliverable");
  assertEquals(row.channel, null);
  assertEquals(row.event_id, 7);
  // email resolves from the stub, so it wins over phone/id as the recorded identifier.
  assertEquals(row.recipient, `${id}@example.test`);
});


// ---------------------------------------------------------------------------
// Proximity. These decide whether a resident is woken at 2am, and both inputs
// are routinely incomplete, so the null cases matter as much as the distances.
// ---------------------------------------------------------------------------

const NODE = { lat: 10.0612, lng: 76.6331 };                 // Kothamangalam sector

Deno.test("withinRadius matches a resident inside the radius", () => {
  assert(withinRadius(NODE, { lat: 10.0700, lng: 76.6400 })); // ~1.2 km
});

Deno.test("withinRadius rejects a resident outside the radius", () => {
  assert(!withinRadius(NODE, { lat: 10.1200, lng: 76.7000 })); // ~9 km
});

Deno.test("withinRadius is inclusive at the boundary and exclusive past it", () => {
  // 0.009 deg of latitude is ~1.0 km, so step along a meridian either side of 3 km.
  assert(withinRadius(NODE, { lat: NODE.lat + 2.9 / 111.32, lng: NODE.lng }));
  assert(!withinRadius(NODE, { lat: NODE.lat + 3.1 / 111.32, lng: NODE.lng }));
});

// The defect this replaced: lat was checked on both sides and lng on neither,
// so two rows with null longitudes had their longitude term collapse to zero
// and matched on latitude alone.
Deno.test("withinRadius does not match two rows that are only half located", () => {
  assert(!withinRadius({ lat: 10.0612, lng: null }, { lat: 10.0620, lng: null }));
  assert(!withinRadius({ lat: 10.0612, lng: null }, { lat: 10.0620, lng: 76.6331 }));
  assert(!withinRadius(NODE, { lat: 10.0620, lng: null }));
});

Deno.test("withinRadius treats an uncommissioned node as unmatchable", () => {
  assert(!withinRadius({ lat: null, lng: null }, { lat: 10.0620, lng: 76.6340 }));
  assert(!withinRadius(null, { lat: 10.0620, lng: 76.6340 }));
  assert(!withinRadius(undefined, { lat: 10.0620, lng: 76.6340 }));
});

Deno.test("withinRadius treats a resident with no location as unmatchable", () => {
  assert(!withinRadius(NODE, { lat: null, lng: null }));
  assert(!withinRadius(NODE, null));
});

// double precision accepts these and the column grant lets a client write them.
Deno.test("withinRadius rejects non-finite coordinates rather than comparing NaN", () => {
  assert(!withinRadius(NODE, { lat: NaN, lng: 76.6331 }));
  assert(!withinRadius(NODE, { lat: Infinity, lng: 76.6331 }));
  assertEquals(kmBetween(NODE, { lat: NaN, lng: 76.6331 }), null);
});

Deno.test("kmBetween is zero at a point and symmetric", () => {
  assertEquals(kmBetween(NODE, NODE), 0);
  const a = { lat: 10.06, lng: 76.63 }, b = { lat: 10.12, lng: 76.70 };
  assertEquals(kmBetween(a, b)!.toFixed(9), kmBetween(b, a)!.toFixed(9));
});
