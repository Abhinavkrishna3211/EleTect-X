import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AuthLayout, authButtonClass, authInputClass } from '@/layouts/AuthLayout'
import { supabase } from '@/lib/supabase'

export function ForgotPassword() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: `${window.location.origin}/reset-password`,
    })
    setSubmitting(false)
    setSent(true)
  }

  return (
    <AuthLayout>
      {!sent ? (
        <>
          <h1 className="m-0 mb-1.5 font-serif text-[28px] font-normal">Reset your password</h1>
          <p className="text-brand-fg/55 m-0 mb-6 font-sans text-sm">
            We'll send a reset link to your email.
          </p>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="email"
              required
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={authInputClass}
            />
            <button type="submit" disabled={submitting} className={authButtonClass}>
              {submitting ? 'Sending…' : 'Send reset link'}
            </button>
          </form>
        </>
      ) : (
        <div className="py-3 text-center">
          <div className="mb-3 text-[32px]">📧</div>
          <h3 className="m-0 mb-2 font-serif text-2xl font-normal">Check your inbox.</h3>
          <p className="text-brand-fg/65 m-0 font-sans text-[14.5px]">
            If an account exists for {email}, a reset link is on its way.
          </p>
        </div>
      )}
      <p className="text-brand-fg/40 m-0 mt-4.5 text-center font-sans text-[13px]">
        <Link to="/login">← Back to login</Link>
      </p>
    </AuthLayout>
  )
}
