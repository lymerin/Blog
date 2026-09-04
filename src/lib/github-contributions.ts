const DAY_IN_MS = 24 * 60 * 60 * 1000
const ISO_DATE_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/

export type ContributionLevel = 0 | 1 | 2 | 3 | 4

export interface Contribution {
  date: string
  count: number
  level: ContributionLevel
}

export interface ContributionResponse {
  total: Record<string, number>
  contributions: Contribution[]
}

export type ContributionWeek = Array<Contribution | null>

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function parseUtcDate(date: string): Date {
  const match = ISO_DATE_PATTERN.exec(date)
  if (!match) throw new Error(`Invalid contribution date: ${date}`)

  const year = Number(match[1])
  const month = Number(match[2])
  const day = Number(match[3])
  const parsed = new Date(Date.UTC(year, month - 1, day))

  if (toIsoDate(parsed) !== date) throw new Error(`Invalid contribution date: ${date}`)
  return parsed
}

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10)
}

function addUtcDays(date: Date, days: number): Date {
  return new Date(date.getTime() + days * DAY_IN_MS)
}

export function normalizeContributionResponse(value: unknown): ContributionResponse {
  if (!isRecord(value) || !Array.isArray(value.contributions)) {
    throw new Error('Invalid GitHub contribution response')
  }

  const byDate = new Map<string, Contribution>()

  for (const item of value.contributions) {
    if (!isRecord(item)) throw new Error('Invalid GitHub contribution item')

    const { date, count, level } = item
    if (typeof date !== 'string') throw new Error('Invalid GitHub contribution date')
    parseUtcDate(date)

    if (typeof count !== 'number' || !Number.isInteger(count) || count < 0) {
      throw new Error(`Invalid contribution count for ${date}`)
    }
    if (typeof level !== 'number' || !Number.isInteger(level) || level < 0 || level > 4) {
      throw new Error(`Invalid contribution level for ${date}`)
    }

    byDate.set(date, { date, count, level: level as ContributionLevel })
  }

  const contributions = [...byDate.values()].sort((left, right) => left.date.localeCompare(right.date))
  if (contributions.length === 0) throw new Error('GitHub contribution response is empty')

  for (let index = 1; index < contributions.length; index += 1) {
    const previous = parseUtcDate(contributions[index - 1].date)
    const current = parseUtcDate(contributions[index].date)
    if (current.getTime() - previous.getTime() !== DAY_IN_MS) {
      throw new Error('GitHub contribution response contains a date gap')
    }
  }

  const total: Record<string, number> = {}
  if (isRecord(value.total)) {
    for (const [key, amount] of Object.entries(value.total)) {
      if (typeof amount === 'number' && Number.isFinite(amount)) total[key] = amount
    }
  }

  return { total, contributions }
}

export function buildContributionWeeks(contributions: Contribution[]): ContributionWeek[] {
  if (contributions.length === 0) return []

  const contributionByDate = new Map(contributions.map((item) => [item.date, item]))
  const firstDate = parseUtcDate(contributions[0].date)
  const lastDate = parseUtcDate(contributions[contributions.length - 1].date)
  const gridStart = addUtcDays(firstDate, -firstDate.getUTCDay())
  const gridEnd = addUtcDays(lastDate, 6 - lastDate.getUTCDay())
  const weeks: ContributionWeek[] = []

  for (let cursor = gridStart; cursor <= gridEnd; cursor = addUtcDays(cursor, 1)) {
    const weekIndex = Math.floor((cursor.getTime() - gridStart.getTime()) / DAY_IN_MS / 7)
    if (!weeks[weekIndex]) weeks[weekIndex] = []
    weeks[weekIndex].push(contributionByDate.get(toIsoDate(cursor)) ?? null)
  }

  return weeks
}
