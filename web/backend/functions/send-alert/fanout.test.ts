// EleTect X — fan-out unit tests. No live project, no network: a stub client stands in for
// Supabase. Run from web/backend/functions/send-alert:
//   deno test --no-check --allow-env fanout.test.ts
// (--allow-env: the test forces channels off via env for determinism; --no-check: skip fetching
//  the type-only supabase-js import so the run is fully offline.)

import { assert, assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { fanOut } from "./fanout.ts";

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
