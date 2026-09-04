import type { MarkdownHeading } from 'astro'
import type { CollectionEntry } from 'astro:content'
import OpenCC from 'opencc-js'
import type { Locale } from '~/i18n'

const toHongKong = OpenCC.Converter({ from: 'cn', to: 'hk' })
const protectedTags = new Set(['code', 'pre', 'script', 'style'])
const urlPattern = /(?:https?:\/\/|mailto:|www\.)[^\s<]+/gi
const htmlTokenPattern = /<!--[\s\S]*?-->|<![^>]*>|<[^>]+>|[^<]+/g

export function convertTextToHongKong(text: string) {
  let converted = ''
  let cursor = 0

  for (const match of text.matchAll(urlPattern)) {
    const index = match.index ?? 0
    converted += toHongKong(text.slice(cursor, index))
    converted += match[0]
    cursor = index + match[0].length
  }

  return converted + toHongKong(text.slice(cursor))
}

export function convertHtmlToHongKong(html: string) {
  let protectedDepth = 0

  return (html.match(htmlTokenPattern) ?? [])
    .map((token) => {
      if (!token.startsWith('<')) {
        return protectedDepth > 0 ? token : convertTextToHongKong(token)
      }

      const tag = token.match(/^<\s*(\/?)\s*([a-zA-Z0-9-]+)/)
      if (!tag) return token

      const [, closing, rawName] = tag
      const name = rawName.toLowerCase()
      if (!protectedTags.has(name)) return token

      if (closing) {
        protectedDepth = Math.max(0, protectedDepth - 1)
      } else if (!token.endsWith('/>')) {
        protectedDepth += 1
      }

      return token
    })
    .join('')
}

export function localizePost(post: CollectionEntry<'posts'>, locale: Locale): CollectionEntry<'posts'> {
  if (locale !== 'zh-hk') return post

  const data = {
    ...post.data,
    title: convertTextToHongKong(post.data.title),
    description: convertTextToHongKong(post.data.description),
    tags: post.data.tags?.map(convertTextToHongKong),
  }

  if (!post.rendered) return { ...post, data }

  const metadata = post.rendered.metadata as
    | (Record<string, unknown> & {
        imagePaths: string[]
        headings?: MarkdownHeading[]
        frontmatter?: Record<string, unknown>
      })
    | undefined

  return {
    ...post,
    data,
    rendered: {
      ...post.rendered,
      html: convertHtmlToHongKong(post.rendered.html),
      metadata: metadata
        ? {
            ...metadata,
            headings: metadata.headings?.map((heading) => ({ ...heading, text: convertTextToHongKong(heading.text) })),
            frontmatter: metadata.frontmatter ? { ...metadata.frontmatter, ...data } : metadata.frontmatter,
          }
        : undefined,
    },
  }
}
