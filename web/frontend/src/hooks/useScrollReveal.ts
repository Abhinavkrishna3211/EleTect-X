import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

// Fade + slight rise as each section scrolls into view.
//
// Three deliberate constraints, because this is a DFO-facing tool and not a
// marketing site:
//
//  1. `prefers-reduced-motion: reduce` short-circuits the whole thing — nothing is
//     hidden, nothing animates, no listener is attached.
//  2. The pre-reveal (hidden) state is applied *from JavaScript*, not from the
//     stylesheet. If the script fails or is blocked, every section stays fully
//     visible rather than the page silently rendering blank — a fade-in must never
//     be able to hide safety information.
//  3. A section is revealed once its top edge is anywhere at or above the fold —
//     including when it is already *behind* the viewport. IntersectionObserver was
//     the obvious tool here and is the wrong one: on an instant jump (End key, an
//     anchor link, a restored scroll position) a section can go from below the fold
//     to above it without the observer ever seeing it intersect, so its state never
//     changes, no callback fires, and it stays at opacity 0 behind the user. A
//     rAF-throttled position check has no such blind spot.

const REVEAL_AT = 0.96 // reveal once the top edge is within the last 4% of the fold

export function useScrollReveal() {
  const { pathname } = useLocation()

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const els = Array.from(document.querySelectorAll<HTMLElement>('main section, [data-reveal]'))
    if (els.length === 0) return

    for (const el of els) el.dataset.reveal = 'pending'

    let pending = els
    const sweep = () => {
      const fold = window.innerHeight * REVEAL_AT
      const next: HTMLElement[] = []
      for (const el of pending) {
        if (el.getBoundingClientRect().top < fold) el.dataset.reveal = 'in'
        else next.push(el)
      }
      pending = next
      if (pending.length === 0) detach()
    }

    let queued = false
    const onScroll = () => {
      if (queued) return
      queued = true
      requestAnimationFrame(() => {
        queued = false
        sweep()
      })
    }

    function detach() {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }

    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll, { passive: true })
    sweep() // reveal whatever is already in view on load

    return detach
  }, [pathname])
}
