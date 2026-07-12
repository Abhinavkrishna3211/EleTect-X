import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout, authButtonClass, authErrorMessage, authInputClass } from '@/layouts/AuthLayout'
import { supabase } from '@/lib/supabase'

// No demo-account list here, deliberately. A public login page that names accounts
// hands a visitor half of a credential pair for free — and one of the entries that
// used to sit here (officer@eletect.in) was a real, officer-role account in the
// production project. Judge/demo logins are issued privately instead; see
// scripts/seed-judge-accounts.mjs. Do not reintroduce this section.
export function Login() {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    setSubmitting(false)
    if (error) {
      setError(authErrorMessage(error))
      return
    }
    navigate('/dashboard')
  }

  return (
    <AuthLayout>
      <h1 className="m-0 mb-1.5 font-serif text-[30px] font-normal">Dashboard login</h1>
      <p className="text-brand-fg/55 m-0 mb-6 font-sans text-sm">Sign in to continue</p>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className={authInputClass}
        />
        <input
          type="password"
          required
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className={authInputClass}
        />
        {error && <p className="text-brand-red m-0 font-sans text-[13px] font-medium">{error}</p>}
        <button type="submit" disabled={submitting} className={authButtonClass}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <p className="m-0 mt-3 text-center font-sans text-[13px]">
        <Link to="/forgot-password" className="text-brand-fg/70 hover:text-brand-fg">
          Forgot password?
        </Link>
      </p>

      <p className="text-brand-fg/40 m-0 mt-6 text-center font-sans text-[13px]">
        <Link to="/">← Back to site</Link>
      </p>
      <p className="text-brand-fg/55 m-0 mt-3.5 text-center font-sans text-sm">
        New here? <Link to="/signup">Sign up</Link>
      </p>
    </AuthLayout>
  )
}
