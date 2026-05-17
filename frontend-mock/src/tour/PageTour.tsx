import { useCallback, useEffect, useState } from 'react'
import Joyride, { STATUS } from 'react-joyride'
import type { CallBackProps, Step } from 'react-joyride'

type PageTourProps = {
  /** Unique key for localStorage — tour runs once per browser until cleared */
  storageKey: string
  steps: Step[]
  /** Delay before starting so layout and fonts are stable */
  delayMs?: number
}

/**
 * First-visit guided tour on the current page. Persists completion in localStorage.
 */
export function PageTour({ storageKey, steps, delayMs = 450 }: PageTourProps) {
  const [run, setRun] = useState(false)

  useEffect(() => {
    if (!steps.length) return
    try {
      if (window.localStorage.getItem(storageKey)) return
    } catch {
      return
    }
    const id = window.setTimeout(() => setRun(true), delayMs)
    return () => window.clearTimeout(id)
  }, [storageKey, steps.length, delayMs])

  const handleCallback = useCallback(
    (data: CallBackProps) => {
      const { status } = data
      if (status === STATUS.FINISHED || status === STATUS.SKIPPED) {
        try {
          window.localStorage.setItem(storageKey, '1')
        } catch {
          /* private mode */
        }
        setRun(false)
      }
    },
    [storageKey]
  )

  if (!steps.length) return null

  return (
    <Joyride
      steps={steps}
      run={run}
      continuous
      showProgress
      showSkipButton
      scrollToFirstStep
      scrollOffset={100}
      disableScrolling={false}
      spotlightClicks={false}
      callback={handleCallback}
      styles={{
        options: {
          zIndex: 10000,
          primaryColor: '#0284c7',
          textColor: '#1e293b',
          overlayColor: 'rgba(15, 23, 42, 0.72)',
          arrowColor: '#fff',
        },
        tooltip: {
          borderRadius: 12,
          fontSize: 14,
        },
        tooltipTitle: {
          fontSize: 16,
          fontWeight: 600,
        },
        buttonNext: {
          borderRadius: 8,
          fontSize: 14,
        },
        buttonBack: {
          borderRadius: 8,
          fontSize: 14,
        },
        buttonSkip: {
          fontSize: 13,
        },
      }}
      locale={{
        back: 'Back',
        close: 'Close',
        last: 'Done',
        next: 'Next',
        skip: 'Skip tour',
      }}
    />
  )
}
