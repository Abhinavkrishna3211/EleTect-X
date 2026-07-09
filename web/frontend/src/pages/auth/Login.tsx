import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AuthLayout, authButtonClass, authInputClass } from '@/layouts/AuthLayout'
import { supabase } from '@/lib/supabase'

const demoAccounts = [
  { label: 'Admin', email: 'admin@eletect.in' },
  { label: 'Forest Officer', email: 'officer@eletect.in' },
  { label: 'Public resident', email: 'resident@eletect.in' },
]

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
      setError(error.message)
      return
    }
    navigate('/dashboard')
  }

  return (
    <AuthLayout>
      <h1 className="m-0 mb-1.5 font-serif text-[30px] font-normal">Dashboard login</h1>
      <p className="text-brand-fg/55 m-0 mb-6 font-sans text-sm">Supabase auth · email + password</p>
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

      <div className="my-5.5 flex items-center gap-3">
        <span className="bg-brand-fg/10 h-px flex-1" />
        <span className="text-brand-fg/40 font-mono text-[11px] font-semibold tracking-[0.12em]">
          DEMO ACCOUNTS
        </span>
        <span className="bg-brand-fg/10 h-px flex-1" />
      </div>
      <div className="flex flex-col gap-2">
        {demoAccounts.map((d) => (
          <button
            key={d.email}
            type="button"
            onClick={() => setEmail(d.email)}
            className="border-brand-fg/12 hover:border-brand-gold flex min-h-12 items-center justify-between rounded-xl border bg-[rgba(15,29,20,0.5)] px-4 py-3.25 transition-colors"
          >
            <span className="font-sans text-sm font-semibold">{d.label}</span>
            <span className="text-brand-fg/45 font-mono text-xs font-medium">{d.email}</span>
          </button>
        ))}
      </div>

      <p className="text-brand-fg/40 m-0 mt-4.5 text-center font-sans text-[13px]">
        <Link to="/">← Back to site</Link>
      </p>
      <p className="text-brand-fg/55 m-0 mt-3.5 text-center font-sans text-sm">
        New here? <Link to="/signup">Sign up</Link>
      </p>
    </AuthLayout>
  )
}
