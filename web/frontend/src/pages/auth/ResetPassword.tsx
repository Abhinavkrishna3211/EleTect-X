import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { AuthLayout, authButtonClass, authErrorMessage, authInputClass } from '@/layouts/AuthLayout'
import { supabase } from '@/lib/supabase'

export function ResetPassword() {
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    const { error } = await supabase.auth.updateUser({ password })
    setSubmitting(false)
    if (error) {
      setError(authErrorMessage(error))
      return
    }
    setDone(true)
  }

  return (
    <AuthLayout>
      {!done ? (
        <>
          <h1 className="m-0 mb-1.5 font-serif text-[28px] font-normal">Set a new password</h1>
          <p className="text-brand-fg/55 m-0 mb-6 font-sans text-sm">
            Choose a new password for your account.
          </p>
          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="password"
              required
              minLength={6}
              placeholder="New password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={authInputClass}
            />
            {error && <p className="text-brand-red m-0 font-sans text-[13px] font-medium">{error}</p>}
            <button type="submit" disabled={submitting} className={authButtonClass}>
              {submitting ? 'Saving…' : 'Save password'}
            </button>
          </form>
        </>
      ) : (
        <div className="py-3 text-center">
          <div className="mb-3 text-[32px]">✅</div>
          <h3 className="m-0 mb-2 font-serif text-2xl font-normal">Password updated.</h3>
          <p className="text-brand-fg/65 m-0 mb-5 font-sans text-[14.5px]">
            You can sign in with your new password now.
          </p>
          <button
            onClick={() => navigate('/login')}
            className="bg-brand-gold hover:bg-brand-gold-hover inline-block rounded-full px-7 py-3.5 font-sans text-sm font-semibold text-[#0B140E] transition-colors"
          >
            Go to sign in
          </button>
        </div>
      )}
    </AuthLayout>
  )
}
