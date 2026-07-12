import { createClient } from '@supabase/supabase-js';

// Service-role client: bypasses RLS by design. This process runs as a
// trusted server-side bridge between ChirpStack and Supabase, equivalent to
// the edge functions in web/backend/functions - it is never exposed to a
// browser, so there is no user session to scope reads/writes to.
export const supabase = createClient(process.env.SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, {
  auth: { persistSession: false },
});
