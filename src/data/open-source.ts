import type { Locale } from '~/i18n'
import openSourceData from './open-source.json'

type LocalizedText = Record<Locale, string>

export type OpenSourceContribution = {
  number: number
  issueNumber?: number
  issueUrl?: string
  title: string
  url: string
  mergedAt: string
  summary: LocalizedText
  author?: string
  article?: string
}

export type OpenSourceProject = {
  slug: string
  name: string
  repository: string
  description: string
  tags: string[]
  contributions: OpenSourceContribution[]
  accent: 'otel' | 'shenyu'
}

export const OPEN_SOURCE_PROJECTS = openSourceData as OpenSourceProject[]

export function getMergedPRLabel(project: OpenSourceProject) {
  const count = project.contributions.length
  return `${count} Merged ${count === 1 ? 'PR' : 'PRs'}`
}

export function getOpenSourceProject(slug: string) {
  return OPEN_SOURCE_PROJECTS.find((project) => project.slug === slug)
}
