import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'

// Fade + slight rise as each section scrolls into view, with the cards inside a
// grid staggering in rather than all appearing at once.
//
// Four deliberate constraints, because this is a DFO-facing tool and not a
// marketing site:
//
//  1. `prefers-reduced-motion: reduce` short-circuits the whole thing — nothing is
//     hidden, nothing animates, no listener is attached.
//  2. The pre-reveal (hidden) state is applied *from JavaScript*, not from the
//     stylesheet. If the script fails or is blocked, every section and every card
//     stays fully visible rather than the page silently rendering blank — a fade-in
//     must never be able to hide safety information.
//  3. A section is revealed once its top edge is anywhere at or above the fold —
//     including when it is already *behind* the viewport. IntersectionObserver was
//     the obvious tool here and is the wrong one: on an instant jump (End key, an
//     anchor link, a restored scroll position) a section can go from below the fold
//     to above it without the observer ever seeing it intersect, so its state never
//     changes, no callback fires, and it stays at opacity 0 behind the user. A
//     rAF-throttled position check has no such blind spot.
//  4. Stagger targets are opted in with `data-reveal-stagger` on the CONTAINER, not
//     auto-detected. Auto-detecting "every grid" is tempting and wrong: Home's
//     comparison table is itself a CSS grid, so that heuristic would stagger
//     individual table cells. The marker keeps the logic here, in one place — pages
//     declare which containers hold cards, they do not implement any of the motion.

const REVEAL_AT = 0.96 // reveal once the top edge is within the last 4% of the fold
const STAGGER_MS = 50 // per-card delay increment
const STAGGER_CAP_MS = 300 // a 7-card grid finishes in 300ms, not 350+

export function useScrollReveal() {
  const { pathname } = useLocation()

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const els = Array.from(document.querySelectorAll<HTMLElement>('main section, [data-reveal]'))
    if (els.length === 0) return

    // Cards inside a marked container: hidden with a per-index delay, released when
    // their section reveals. Nested containers are fine — each indexes its own children.
    const itemsFor = new Map<HTMLElement, HTMLElement[]>()

    for (const el of els) {
      el.dataset.reveal = 'pending'

      const items: HTMLElement[] = []
      for (const container of el.querySelectorAll<HTMLElement>('[data-reveal-stagger]')) {
        const children = Array.from(container.children).filter(
          (c): c is HTMLElement => c instanceof HTMLElement,
        )
        children.forEach((child, i) => {
          child.dataset.revealItem = 'pending'
          child.style.setProperty('--reveal-delay', `${Math.min(i * STAGGER_MS, STAGGER_CAP_MS)}ms`)
          items.push(child)
        })
      }
      itemsFor.set(el, items)
    }

    let pending = els
    const reveal = (el: HTMLElement) => {
      el.dataset.reveal = 'in'
      for (const item of itemsFor.get(el) ?? []) item.dataset.revealItem = 'in'
    }

    const sweep = () => {
      const fold = window.innerHeight * REVEAL_AT
      const next: HTMLElement[] = []
      for (const el of pending) {
        if (el.getBoundingClientRect().top < fold) reveal(el)
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
