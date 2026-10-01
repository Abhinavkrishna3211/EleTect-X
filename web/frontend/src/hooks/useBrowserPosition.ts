import { useState } from 'react'

// One wrapper over navigator.geolocation, used by both things that need a
// position: an admin placing a node (NodePlacementForm) and a resident setting
// their home (ResidentView). Neither should carry its own copy of the error
// mapping - the failures are a property of the API and of being in a forest,
// not of the caller.

// getCurrentPosition can sit indefinitely waiting on a cold GPS lock. Fifteen
// seconds is long enough for one under open sky and short enough that a failure
// under canopy is reported rather than hung on.
const FIX_TIMEOUT_MS = 15_000

export interface BrowserFix {
  lat: number
  lng: number
  accuracy: number
}

function describe(err: GeolocationPositionError): string {
  switch (err.code) {
    case err.PERMISSION_DENIED:
      return 'Location permission denied. Allow it for this site in your browser settings and try again.'
    case err.POSITION_UNAVAILABLE:
      return 'No fix available here - tree cover and indoor walls both block GPS. Try again outside.'
    case err.TIMEOUT:
      return 'Timed out waiting for a fix. Try again under open sky.'
    default:
      return err.message || 'Could not read a location.'
  }
}

export function useBrowserPosition() {
  const [locating, setLocating] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function request(onFix: (fix: BrowserFix) => void) {
    // Geolocation needs a secure context; over plain http the API is simply
    // absent rather than failing with a code.
    if (!navigator.geolocation) {
      setError('This browser will not share a location over an insecure connection.')
      return
    }
    setLocating(true)
    setError(null)
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocating(false)
        onFix({ lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy })
      },
      (err) => {
        setLocating(false)
        setError(describe(err))
      },
      { enableHighAccuracy: true, timeout: FIX_TIMEOUT_MS, maximumAge: 0 },
    )
  }

  return { locating, error, setError, request }
}
