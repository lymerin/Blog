'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { cn } from '~/lib/utils'
import {
  buildContributionWeeks,
  normalizeContributionResponse,
  type Contribution,
  type ContributionLevel,
} from '~/lib/github-contributions'
import Tooltip, { TooltipProvider } from './Tooltip.tsx'

// API from https://github.com/grubersjoe/github-contributions-api
interface ErrorData {
  error: string
}

interface Props {
  username: string
  tooltipEnabled: boolean
  locale: 'zh-cn' | 'zh-hk'
}

async function fetchContributions(username: string, signal: AbortSignal): Promise<Contribution[]> {
  const response = await fetch(`https://github-contributions-api.jogruber.de/v4/${username}?y=last`, {
    signal,
    cache: 'no-store',
  })
  const data: unknown = await response.json()

  if (!response.ok) {
    const message = typeof (data as ErrorData)?.error === 'string' ? (data as ErrorData).error : response.statusText
    throw Error(`Fetching GitHub contribution data for "${username}" failed: ${message}`)
  }

  return normalizeContributionResponse(data).contributions
}

const levelClasses: Record<ContributionLevel, string> = {
  0: 'bg-zinc-200/70 dark:bg-zinc-900',
  1: 'bg-zinc-400/70 dark:bg-zinc-700',
  2: 'bg-zinc-500/80 dark:bg-zinc-500',
  3: 'bg-zinc-700 dark:bg-zinc-300',
  4: 'bg-zinc-900 dark:bg-zinc-50',
}

export default function GithubContributions({ username, tooltipEnabled, locale }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [contributions, setContributions] = useState<Contribution[] | null>(null)
  const [hasError, setHasError] = useState(false)
  const [retryCount, setRetryCount] = useState(0)
  const weeks = useMemo(() => buildContributionWeeks(contributions ?? []), [contributions])
  const languageTag = locale === 'zh-hk' ? 'zh-HK' : 'zh-CN'
  const copy =
    locale === 'zh-hk'
      ? { error: '暫時無法載入 GitHub Contributions。', retry: '重試', view: '查看 GitHub', unit: '次貢獻' }
      : { error: '暂时无法加载 GitHub Contributions。', retry: '重试', view: '查看 GitHub', unit: '次贡献' }

  const scrollToRight = useCallback(() => {
    if (containerRef.current) {
      containerRef.current.scrollLeft = containerRef.current.scrollWidth
    }
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 10000)

    setHasError(false)
    fetchContributions(username, controller.signal)
      .then((nextContributions) => setContributions(nextContributions))
      .catch(() => setHasError(true))
      .finally(() => window.clearTimeout(timeout))

    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [username, retryCount])

  useEffect(scrollToRight, [weeks, scrollToRight])

  if (hasError) {
    return (
      <div className="mx-2 max-md:mx-0 rounded-lg border border-border/70 px-4 py-5 text-sm text-muted-foreground">
        <p>{copy.error}</p>
        <div className="mt-3 flex gap-4">
          <button type="button" className="text-foreground transition-colors hover:text-primary" onClick={() => setRetryCount((count) => count + 1)}>
            {copy.retry}
          </button>
          <a className="transition-colors hover:text-primary" href={`https://github.com/${username}`} target="_blank" rel="noopener noreferrer">
            {copy.view} ↗
          </a>
        </div>
      </div>
    )
  }

  if (!contributions) {
    return (
      <div className="grid grid-flow-col gap-1 overflow-hidden py-2 px-2 max-md:px-0" aria-hidden="true">
        {Array.from({ length: 53 }, (_, weekIndex) => (
          <div key={weekIndex} className="grid grid-rows-7 gap-1">
            {Array.from({ length: 7 }, (_, dayIndex) => (
              <div key={dayIndex} className="size-2 animate-pulse rounded-[1px] bg-zinc-200/70 dark:bg-zinc-900" />
            ))}
          </div>
        ))}
      </div>
    )
  }

  return (
    <TooltipProvider>
      <div
        ref={containerRef}
        className="grid grid-flow-col gap-1 overflow-x-auto py-2 px-2 max-md:px-0 scroll-smooth"
        aria-label="GitHub contribution calendar"
      >
        {weeks.map((week, weekIndex) => (
          <div key={weekIndex} className="grid grid-rows-7 gap-1">
            {week.map((contribution, dayIndex) => {
              if (!contribution) return <div key={`empty-${weekIndex}-${dayIndex}`} className="size-2" aria-hidden="true" />

              const { date, count, level } = contribution
              const formattedDate = new Date(`${date}T00:00:00Z`).toLocaleDateString(languageTag, {
                weekday: 'long',
                year: 'numeric',
                month: 'long',
                day: 'numeric',
                timeZone: 'UTC',
              })
              const tooltipContent = `${formattedDate} · ${count} ${copy.unit}`

              return (
                <Tooltip key={date} content={tooltipContent} disabled={!tooltipEnabled}>
                  <div
                    className={cn('size-2 relative rounded-[1px] transition-colors duration-300', levelClasses[level])}
                    data-date={date}
                    data-count={count}
                    data-level={level}
                    aria-label={tooltipContent}
                  />
                </Tooltip>
              )
            })}
          </div>
        ))}
      </div>
    </TooltipProvider>
  )
}
