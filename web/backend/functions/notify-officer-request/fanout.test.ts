// EleTect X — officer-request fan-out unit tests. No live project, no network: unlike
// send-alert's channels, sendEmail here has no enable-gate to switch off, so fetch is stubbed
// globally for the duration of each test and restored afterward. Run from
// web/backend/functions/notify-officer-request:
//   deno test --no-check --allow-env fanout.test.ts
// (--allow-env: ALERT_EMAIL_FROM/RESEND_API_KEY are read via Deno.env.get inside sendEmail;
//  --no-check: skip fetching the type-only supabase-js import so the run is fully offline.)

import { assert, assertEquals } from "https://deno.land/std@0.224.0/assert/mod.ts";
import { fanOut } from "./fanout.ts";

// Minimal stand-in for the one SupabaseClient surface fanOut touches: auth.admin.getUserById.
// getUserById rejects for `poisonId` to simulate a lookup failure.
function makeStub(poisonId: string) {
  const lookups: string[] = [];
  const client = {
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
  return { client, lookups };
}

// sendEmail (fanout.ts) calls fetch unconditionally — no CHANNEL_EMAIL-style gate exists in this
// function, unlike send-alert's emailChannel. Swap the global for the duration of one run so no
// real network happens, and always restore it, pass or fail.
async function withStubbedFetch<T>(
  impl: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
  run: () => Promise<T>,
): Promise<T> {
  const real = globalThis.fetch;
  globalThis.fetch = impl as typeof fetch;
  try {
    return await run();
  } finally {
    globalThis.fetch = real;
  }
}

Deno.test("fanOut: a getUserById failure skips only that admin, not the rest of the batch", async () => {
  const before = "11111111-1111-1111-1111-111111111111";
  const poison = "22222222-2222-2222-2222-222222222222";
  const after = "33333333-3333-3333-3333-333333333333";
  const { client, lookups } = makeStub(poison);

  const sentTo: string[] = [];
  const result = await withStubbedFetch(
    (_input, init) => {
      const body = JSON.parse(String(init?.body ?? "{}"));
      sentTo.push(body.to);
      return Promise.resolve(new Response(null, { status: 200 }));
    },
    () =>
      fanOut(
        client as unknown as Parameters<typeof fanOut>[0],
        [{ id: before }, { id: poison }, { id: after }],
        { subject: "s", body: "b" },
      ),
  );

  // The failure did not propagate — fanOut resolved rather than throwing.
  // Every admin was attempted, in order, the poison one included.
  assertEquals(lookups, [before, poison, after]);

  // The admin AFTER the failure still got emailed: the batch was not taken out.
  assertEquals(sentTo.sort(), [`${before}@example.test`, `${after}@example.test`].sort());

  // The poison admin produced no send attempt at all (skipped, not half-processed).
  assert(!sentTo.includes(`${poison}@example.test`));
  assertEquals(result.notified, 2);
});

Deno.test("fanOut: notified only counts sends that actually succeeded", async () => {
  const admin1 = "44444444-4444-4444-4444-444444444444";
  const admin2 = "55555555-5555-5555-5555-555555555555";
  const { client } = makeStub("none");

  let calls = 0;
  const result = await withStubbedFetch(
    (_input, _init) => {
      calls++;
      // First send bounces (simulated Resend rejection), second goes through.
      return Promise.resolve(new Response(null, { status: calls === 1 ? 422 : 200 }));
    },
    () =>
      fanOut(
        client as unknown as Parameters<typeof fanOut>[0],
        [{ id: admin1 }, { id: admin2 }],
        { subject: "s", body: "b" },
      ),
  );

  assertEquals(calls, 2);
  assertEquals(result.notified, 1);
});


// ---------------------------------------------------------------------------
// Deactivated admins. Same defect and same fix as send-alert's fanOut: the
// recipient query selects on role, which admin_set_deactivated() does not
// touch, so without the skip a revoked admin keeps receiving every officer
// applicant's name, department, official email and phone. Asserted on the
// addresses fetch was actually called with, which is the thing that leaked.
// ---------------------------------------------------------------------------

function makeBanStub(bans: Record<string, string | null>) {
  const client = {
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
  return { client };
}

// Collect every address sendEmail actually tried, with no network.
function runFanOut(client: unknown, admins: { id: string }[]) {
  const sentTo: string[] = [];
  return withStubbedFetch(
    (_input, init) => {
      sentTo.push(JSON.parse(String(init?.body ?? "{}")).to);
      return Promise.resolve(new Response(null, { status: 200 }));
    },
    () =>
      fanOut(
        client as unknown as Parameters<typeof fanOut>[0],
        admins,
        { subject: "s", body: "b" },
      ),
  ).then((result) => ({ result, sentTo }));
}

Deno.test("fanOut: a deactivated admin is skipped, an active one still receives", async () => {
  const active = "11111111-0000-0000-0000-0000000000a1";
  const banned = "22222222-0000-0000-0000-0000000000b2";
  const future = new Date(Date.now() + 86_400_000).toISOString();

  const { client } = makeBanStub({ [banned]: future });
  const { result, sentTo } = await runFanOut(client, [{ id: active }, { id: banned }]);

  assertEquals(sentTo, [`${active}@example.test`]);
  assert(!sentTo.includes(`${banned}@example.test`));
  assertEquals(result.notified, 1);
});

Deno.test("fanOut: an unparseable banned_until counts as banned", async () => {
  // 'infinity' is what admin_set_deactivated() writes; Date.parse gives NaN.
  const banned = "33333333-0000-0000-0000-0000000000c3";
  const { client } = makeBanStub({ [banned]: "infinity" });
  const { result, sentTo } = await runFanOut(client, [{ id: banned }]);

  assertEquals(sentTo, []);
  assertEquals(result.notified, 0);
});

Deno.test("fanOut: an expired ban and a null ban both still receive", async () => {
  const lapsed = "44444444-0000-0000-0000-0000000000d4";
  const never = "55555555-0000-0000-0000-0000000000e5";
  const past = new Date(Date.now() - 86_400_000).toISOString();

  const { client } = makeBanStub({ [lapsed]: past, [never]: null });
  const { result, sentTo } = await runFanOut(client, [{ id: lapsed }, { id: never }]);

  assertEquals(sentTo.sort(), [`${lapsed}@example.test`, `${never}@example.test`].sort());
  assertEquals(result.notified, 2);
});
