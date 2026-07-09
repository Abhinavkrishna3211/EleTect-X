import { Link } from 'react-router-dom'
import type { ReactNode } from 'react'
import { isAuthRetryableFetchError } from '@supabase/supabase-js'

export const authInputClass =
  'min-h-11 rounded-xl border border-brand-fg/15 bg-brand-bg px-4 py-3.75 font-sans text-[15px] text-brand-fg placeholder:text-brand-fg/40 focus:border-brand-gold focus:outline-none'

export const authButtonClass =
  'bg-brand-gold hover:bg-brand-gold-hover min-h-12 rounded-full px-4 py-3.75 font-sans text-[15px] font-semibold text-[#0B140E] transition-colors disabled:cursor-not-allowed disabled:opacity-60'

// supabase-js reports 5xx responses as a generic "retryable" error and stringifies
// the raw fetch Response for its message ("{}"), so surface a readable fallback instead.
export function authErrorMessage(error: { message: string }) {
  return isAuthRetryableFetchError(error)
    ? 'Something went wrong on our end. Please try again in a moment.'
    : error.message
}

export function AuthLayout({ children, maxWidth = 420 }: { children: ReactNode; maxWidth?: number }) {
  return (
    <div
      className="grid min-h-screen place-items-center px-6 py-10"
      style={{ background: 'radial-gradient(100% 80% at 50% 0%, #0F1D14 0%, #070D0A 70%)' }}
    >
      <div className="w-full" style={{ maxWidth }}>
        <Link to="/" className="text-brand-fg mb-7 flex items-center justify-center gap-2.5">
          <img src="/assets/logo.png" alt="EleTect logo" className="h-12.25 w-12.25 rounded-full object-cover" />
          <span className="font-sans text-xl font-semibold">EleTect</span>
        </Link>
        <div className="border-brand-fg/10 rounded-[20px] border bg-[#0B0D0B] p-6 sm:p-9">{children}</div>
      </div>
    </div>
  )
}
