import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'

interface Options {
  // PostgREST ordering column + direction for the initial fetch.
  orderBy?: { column: string; ascending?: boolean }
  limit?: number
}

// Loads a table once, then keeps it live over Supabase Realtime. Rows are held
// in a Map keyed by their primary key so INSERT/UPDATE upsert and DELETE removes
// in place. The tables used here (nodes, events) are already in the
// supabase_realtime publication (see schema.sql). Returns rows newest-first when
// orderBy is descending; the caller can re-sort as needed.
export function useRealtimeTable<T>(
  table: string,
  primaryKey: keyof T & string,
  options: Options = {},
) {
  const [rows, setRows] = useState<Map<string, T>>(new Map())
  const [loading, setLoading] = useState(true)

  const { orderBy, limit } = options
  const orderCol = orderBy?.column
  const orderAsc = orderBy?.ascending ?? false

  useEffect(() => {
    let active = true

    async function load() {
      let query = supabase.from(table).select('*')
      if (orderCol) query = query.order(orderCol, { ascending: orderAsc })
      if (limit) query = query.limit(limit)
      const { data } = await query
      if (!active) return
      const next = new Map<string, T>()
      for (const row of (data ?? []) as T[]) next.set(String(row[primaryKey]), row)
      setRows(next)
      setLoading(false)
    }
    load()

    const channel = supabase
      .channel(`realtime:${table}`)
      .on('postgres_changes', { event: '*', schema: 'public', table }, (payload) => {
        setRows((prev) => {
          const next = new Map(prev)
          if (payload.eventType === 'DELETE') {
            const old = payload.old as T
            next.delete(String(old[primaryKey]))
          } else {
            const row = payload.new as T
            next.set(String(row[primaryKey]), row)
          }
          return next
        })
      })
      .subscribe()

    return () => {
      active = false
      supabase.removeChannel(channel)
    }
  }, [table, primaryKey, orderCol, orderAsc, limit])

  return { rows, loading }
}
