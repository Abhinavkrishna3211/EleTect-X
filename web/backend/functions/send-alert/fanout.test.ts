// EleTect X — fan-out unit tests. No live project, no network: a stub client stands in for
// Supabase. Run from web/backend/functions/send-alert:
//   deno test --no-check --allow-env fanout.test.ts
// (--allow-env: the test forces channels off via env for determinism; --no-check: skip fetching
//  the type-only supabase-js import so the run is fully offline.)

import { assert, assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { deliver, fanOut, kmBetween, withinRadius } from "./fanout.ts";

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


// ---------------------------------------------------------------------------
// Multi-channel delivery. A 'critical' event sends on every channel a recipient
// has rather than stopping at the first that works.
//
// These stub globalThis.fetch rather than reaching a provider, so the run stays
// offline. The test is deliberately run without --allow-net: if a channel ever
// escapes the stub, it fails on a permission error instead of quietly sending a
// real message from a test.
// ---------------------------------------------------------------------------

function withStubbedChannels<T>(run: () => Promise<T>): Promise<T> {
  const realFetch = globalThis.fetch;
  const before = {
    email: Deno.env.get("CHANNEL_EMAIL"),
    sms: Deno.env.get("CHANNEL_SMS"),
    whatsapp: Deno.env.get("CHANNEL_WHATSAPP"),
    resend: Deno.env.get("RESEND_API_KEY"),
    smsKey: Deno.env.get("SMS_API_KEY"),
  };
  Deno.env.delete("CHANNEL_EMAIL");          // email is on whenever RESEND_API_KEY is set
  Deno.env.set("RESEND_API_KEY", "test-key");
  Deno.env.set("CHANNEL_SMS", "on");
  Deno.env.set("SMS_API_KEY", "test-key");
  Deno.env.delete("CHANNEL_WHATSAPP");       // stays off: its send() is a stub that always fails
  globalThis.fetch = () => Promise.resolve(new Response("{}", { status: 200 }));

  const restore = () => {
    globalThis.fetch = realFetch;
    for (const [k, v] of Object.entries({
      CHANNEL_EMAIL: before.email, CHANNEL_SMS: before.sms, CHANNEL_WHATSAPP: before.whatsapp,
      RESEND_API_KEY: before.resend, SMS_API_KEY: before.smsKey,
    })) v === undefined ? Deno.env.delete(k) : Deno.env.set(k, v);
  };
  return run().finally(restore);
}

const REACHABLE = { id: "aaaaaaaa-0000-0000-0000-000000000001", phone: "+919999999999", email: "a@example.test" };

Deno.test("deliver: an ordinary alert stops at the first channel that accepts", async () => {
  await withStubbedChannels(async () => {
    const { client, inserts } = makeStub("none");
    const via = await deliver(
      client as unknown as Parameters<typeof deliver>[0], REACHABLE, { subject: "s", body: "b" }, 7,
    );
    assertEquals(via, ["email"]);
    // One attempt logged, and SMS was never tried even though the number is reachable.
    assertEquals(inserts.map((i) => i.row.channel), ["email"]);
  });
});

Deno.test("deliver: a critical alert sends on every channel the recipient has", async () => {
  await withStubbedChannels(async () => {
    const { client, inserts } = makeStub("none");
    const via = await deliver(
      client as unknown as Parameters<typeof deliver>[0], REACHABLE, { subject: "s", body: "b" }, 7, true,
    );
    assertEquals(via, ["email", "sms"]);
    assertEquals(inserts.map((i) => i.row.channel), ["email", "sms"]);
    // Both are 'sent' - neither is a fallback after a failure.
    assertEquals(inserts.map((i) => i.row.status), ["sent", "sent"]);
  });
});

Deno.test("deliver: everyChannel still records undeliverable when nothing accepts", async () => {
  const before = Deno.env.get("CHANNEL_EMAIL");
  Deno.env.set("CHANNEL_EMAIL", "off");
  Deno.env.delete("CHANNEL_SMS");
  try {
    const { client, inserts } = makeStub("none");
    const via = await deliver(
      client as unknown as Parameters<typeof deliver>[0], REACHABLE, { subject: "s", body: "b" }, 7, true,
    );
    assertEquals(via, []);
    assertEquals(inserts.length, 1);
    assertEquals(inserts[0].row.status, "undeliverable");
    assertEquals(inserts[0].row.channel, null);
  } finally {
    before === undefined ? Deno.env.delete("CHANNEL_EMAIL") : Deno.env.set("CHANNEL_EMAIL", before);
  }
});

// The count that goes back to the webhook caller. One person reached twice is
// one person warned; reporting 2 would read as better coverage than there is.
Deno.test("fanOut: sent counts people reached, byChannel counts accepted attempts", async () => {
  await withStubbedChannels(async () => {
    const { client } = makeStub("none");
    const result = await fanOut(
      client as unknown as Parameters<typeof fanOut>[0],
      [{ id: REACHABLE.id, phone: REACHABLE.phone }],
      { subject: "s", body: "b" },
      7,
      true,
    );
    assertEquals(result.sent, 1);
    assertEquals(result.byChannel, { email: 1, sms: 1 });
  });
});


// ---------------------------------------------------------------------------
// Deactivated recipients. admin_set_deactivated() writes auth.users.banned_until
// and leaves profiles.role alone, so a revoked officer still matches every
// recipient query. These pin the skip, and in particular pin it closed: the
// fail-open direction is the one that leaks, and it is the one a later
// refactor would reintroduce by "simplifying" the unparseable case away.
// ---------------------------------------------------------------------------

// Like makeStub, but every lookup succeeds and carries a banned_until from the map.
function makeBanStub(bans: Record<string, string | null>) {
  const inserts: { table: string; row: Record<string, unknown> }[] = [];
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
          return Promise.resolve({
            data: { user: { id, email: `${id}@example.test`, banned_until: bans[id] ?? null } },
            error: null,
          });
        },
      },
    },
  };
  return { client, inserts };
}

function reached(inserts: { table: string; row: Record<string, unknown> }[]) {
  return inserts.filter((i) => i.table === "alerts").map((i) => i.row.recipient).sort();
}

// Channels off: every recipient that gets through lands exactly one audit row,
// so the row list is a faithful record of who was not skipped.
function channelsOff() {
  Deno.env.set("CHANNEL_EMAIL", "off");
  Deno.env.delete("CHANNEL_SMS");
  Deno.env.delete("CHANNEL_WHATSAPP");
}

Deno.test("fanOut: a deactivated recipient is skipped and the rest of the batch is not", async () => {
  channelsOff();

  const active = "11111111-0000-0000-0000-00000000000a";
  const banned = "22222222-0000-0000-0000-00000000000b";
  const future = new Date(Date.now() + 86_400_000).toISOString();

  const { client, inserts } = makeBanStub({ [banned]: future });
  await fanOut(
    client as unknown as Parameters<typeof fanOut>[0],
    [{ id: active, phone: null }, { id: banned, phone: null }],
    { subject: "s", body: "b" },
    1,
  );

  // No row at all for the deactivated account - not even an undeliverable one,
  // because it never became a recipient.
  assertEquals(reached(inserts), [`${active}@example.test`]);
});

Deno.test("fanOut: an unparseable banned_until counts as banned", async () => {
  channelsOff();

  // 'infinity' is exactly what admin_set_deactivated() writes, and Date.parse
  // returns NaN for it. Failing closed costs a deactivated account one missed
  // email; failing open keeps mailing someone whose access was revoked.
  const banned = "33333333-0000-0000-0000-00000000000c";
  const { client, inserts } = makeBanStub({ [banned]: "infinity" });
  await fanOut(
    client as unknown as Parameters<typeof fanOut>[0],
    [{ id: banned, phone: null }],
    { subject: "s", body: "b" },
    2,
  );

  assertEquals(reached(inserts), []);
});

Deno.test("fanOut: an expired ban and a null ban both still receive", async () => {
  channelsOff();

  // banned_until in the past means the ban lapsed; null means there never was
  // one. Neither is a reason to withhold an alert.
  const lapsed = "44444444-0000-0000-0000-00000000000d";
  const never = "55555555-0000-0000-0000-00000000000e";
  const past = new Date(Date.now() - 86_400_000).toISOString();

  const { client, inserts } = makeBanStub({ [lapsed]: past, [never]: null });
  await fanOut(
    client as unknown as Parameters<typeof fanOut>[0],
    [{ id: lapsed, phone: null }, { id: never, phone: null }],
    { subject: "s", body: "b" },
    3,
  );

  assertEquals(reached(inserts), [`${lapsed}@example.test`, `${never}@example.test`].sort());
});
