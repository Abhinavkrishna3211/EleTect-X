import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { AuthLayout, authButtonClass, authErrorMessage, authInputClass } from '@/layouts/AuthLayout'
import { supabase } from '@/lib/supabase'

type SignupRole = 'resident' | 'officer'
type Done = 'none' | 'resident' | 'officer'

export function Signup() {
  const [role, setRole] = useState<SignupRole>('resident')
  const [done, setDone] = useState<Done>('none')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [suName, setSuName] = useState('')
  const [suPhone, setSuPhone] = useState('')
  const [suEmail, setSuEmail] = useState('')
  const [suPass, setSuPass] = useState('')

  const [ofName, setOfName] = useState('')
  const [ofDept, setOfDept] = useState('')
  const [ofDesignation, setOfDesignation] = useState('')
  const [ofEmail, setOfEmail] = useState('')
  const [ofPhone, setOfPhone] = useState('')
  const [ofPass, setOfPass] = useState('')

  // Honeypot: real users never see or fill this field (moved off-screen, not display:none,
  // since some scripted bots skip fields hidden that way). A filled value means a bot filled
  // every input it found — reject silently, no error, no network call, don't tip it off.
  const [hp, setHp] = useState('')

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    if (hp) return
    setError('')
    setSubmitting(true)

    if (role === 'resident') {
      const { error } = await supabase.auth.signUp({
        email: suEmail,
        password: suPass,
        options: { data: { full_name: suName, phone: suPhone } },
      })
      setSubmitting(false)
      if (error) {
        setError(authErrorMessage(error))
        return
      }
      setDone('resident')
    } else {
      const { error } = await supabase.auth.signUp({
        email: ofEmail,
        password: ofPass,
        options: {
          data: {
            full_name: ofName,
            phone: ofPhone,
            officer_request: true,
            department: ofDept,
            designation: ofDesignation,
            official_email: ofEmail,
          },
        },
      })
      setSubmitting(false)
      if (error) {
        setError(authErrorMessage(error))
        return
      }
      setDone('officer')
    }
  }

  return (
    <AuthLayout maxWidth={460}>
      {done === 'none' && (
        <>
          <h1 className="m-0 mb-1.5 font-serif text-[30px] font-normal">Create your account</h1>
          <p className="text-brand-fg/55 m-0 mb-5.5 font-sans text-sm">
            Choose the account type that fits you.
          </p>
          <div className="border-brand-fg/15 mb-5.5 flex overflow-hidden rounded-xl border">
            <button
              type="button"
              onClick={() => setRole('resident')}
              className={`flex-1 py-3.25 font-sans text-[13.5px] font-semibold transition-colors ${
                role === 'resident' ? 'bg-brand-gold text-[#0B140E]' : 'bg-transparent text-brand-fg/70'
              }`}
            >
              Resident
            </button>
            <button
              type="button"
              onClick={() => setRole('officer')}
              className={`flex-1 py-3.25 font-sans text-[13.5px] font-semibold transition-colors ${
                role === 'officer' ? 'bg-brand-gold text-[#0B140E]' : 'bg-transparent text-brand-fg/70'
              }`}
            >
              Forest Officer
            </button>
          </div>

          <form onSubmit={handleSubmit} className="flex flex-col gap-3">
            <input
              type="text"
              name="company"
              value={hp}
              onChange={(e) => setHp(e.target.value)}
              tabIndex={-1}
              autoComplete="off"
              aria-hidden="true"
              className="absolute left-[-9999px] h-0 w-0 opacity-0"
            />
            {role === 'resident' ? (
              <>
                <input
                  required
                  placeholder="Full name"
                  value={suName}
                  onChange={(e) => setSuName(e.target.value)}
                  className={authInputClass}
                />
                <input
                  type="tel"
                  required
                  placeholder="Phone number (+91…)"
                  value={suPhone}
                  onChange={(e) => setSuPhone(e.target.value)}
                  className={authInputClass}
                />
                <input
                  type="email"
                  required
                  placeholder="Email"
                  value={suEmail}
                  onChange={(e) => setSuEmail(e.target.value)}
                  className={authInputClass}
                />
                <input
                  type="password"
                  required
                  minLength={6}
                  placeholder="Create a password"
                  value={suPass}
                  onChange={(e) => setSuPass(e.target.value)}
                  className={authInputClass}
                />
              </>
            ) : (
              <>
                <input
                  required
                  placeholder="Full name"
                  value={ofName}
                  onChange={(e) => setOfName(e.target.value)}
                  className={authInputClass}
                />
                <input
                  required
                  placeholder="Department (e.g. Kerala Forest Department)"
                  value={ofDept}
                  onChange={(e) => setOfDept(e.target.value)}
                  className={authInputClass}
                />
                <input
                  required
                  placeholder="Designation (e.g. Range Forest Officer)"
                  value={ofDesignation}
                  onChange={(e) => setOfDesignation(e.target.value)}
                  className={authInputClass}
                />
                <input
                  type="email"
                  required
                  placeholder="Official email (…@keralaforest.gov.in)"
                  value={ofEmail}
                  onChange={(e) => setOfEmail(e.target.value)}
                  className={authInputClass}
                />
                <input
                  type="tel"
                  required
                  placeholder="Phone number"
                  value={ofPhone}
                  onChange={(e) => setOfPhone(e.target.value)}
                  className={authInputClass}
                />
                <input
                  type="password"
                  required
                  minLength={6}
                  placeholder="Create a password"
                  value={ofPass}
                  onChange={(e) => setOfPass(e.target.value)}
                  className={authInputClass}
                />
                <p className="text-brand-fg/45 m-0 font-sans text-[12.5px] leading-relaxed">
                  Officer accounts are reviewed by an EleTect admin before dashboard access is granted.
                </p>
              </>
            )}

            {error && <p className="text-brand-red m-0 mt-1 font-sans text-[13px] font-medium">{error}</p>}
            <button type="submit" disabled={submitting} className={`${authButtonClass} mt-1.5 w-full`}>
              {submitting ? 'Signing up…' : 'Sign up'}
            </button>
          </form>
        </>
      )}

      {done === 'resident' && (
        <div className="py-3 text-center">
          <div className="mb-3 text-[32px]">✅</div>
          <h3 className="m-0 mb-2 font-serif text-2xl font-normal">Account created.</h3>
          <p className="text-brand-fg/65 m-0 mb-5 font-sans text-[14.5px]">
            You can sign in with your email now.
          </p>
          <Link
            to="/login"
            className="bg-brand-gold hover:bg-brand-gold-hover inline-block rounded-full px-7 py-3.5 font-sans text-sm font-semibold text-[#0B140E] transition-colors"
          >
            Go to sign in
          </Link>
        </div>
      )}

      {done === 'officer' && (
        <div className="py-3 text-center">
          <div className="mb-3 text-[32px]">⏳</div>
          <h3 className="m-0 mb-2 font-serif text-2xl font-normal">Pending approval.</h3>
          <p className="text-brand-fg/65 m-0 font-sans text-[14.5px] leading-relaxed">
            Thanks, {ofName}. An EleTect admin will review your department and designation before granting
            dashboard access. You'll be notified by email once approved.
          </p>
        </div>
      )}

      <p className="text-brand-fg/40 m-0 mt-4.5 text-center font-sans text-[13px]">
        <Link to="/login">← Back to login</Link>
      </p>
    </AuthLayout>
  )
}
