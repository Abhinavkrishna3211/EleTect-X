import { describe, expect, it } from 'vitest'
import loginSource from './Login.tsx?raw'

describe('Login page source', () => {
  it('never renders a real @eletect.in address', () => {
    // The public login page must never name a real account - see
    // docs/WEBAPP_COMPLETION_PLAN.md's officer@eletect.in finding: a demo-account
    // hint list here once handed every visitor a confirmed-valid staff username.
    // Source-scan rather than a rendered check - this suite runs pure Node, no
    // jsdom (vite.config.ts), and this page has no dynamic email source to render.
    // Comments are stripped first: this file's own header comment documents that
    // finding by name, and a comment never reaches the browser.
    const withoutComments = loginSource.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
    expect(withoutComments).not.toMatch(/[\w.+-]+@eletect\.in/)
  })
})
