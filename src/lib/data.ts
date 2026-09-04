import { getCollection, type CollectionEntry } from 'astro:content'
import type { Locale } from '~/i18n'
import { localizePost } from '~/lib/opencc'

// 文章按时间排序
export function postsSort(posts: CollectionEntry<'posts'>[]) {
  return posts.slice().sort((a, b) => {
    const dateA = a.data.updatedDate ?? a.data.pubDate
    const dateB = b.data.updatedDate ?? b.data.pubDate
    return new Date(dateB).getTime() - new Date(dateA).getTime()
  })
}

function isPostVisible(post: CollectionEntry<'posts'>) {
  return !post.data.draft || import.meta.env.DEV
}

// 获取所有非草稿文章，按时间排序
export async function getAllPosts(locale: Locale = 'zh-cn'): Promise<CollectionEntry<'posts'>[]> {
  const allPosts = await getCollection('posts')
  return postsSort(allPosts.filter(isPostVisible)).map((post) => localizePost(post, locale))
}

// 获取所有置顶文章
export async function getPinnedPosts(locale: Locale = 'zh-cn'): Promise<CollectionEntry<'posts'>[]> {
  const allPosts = await getCollection('posts')
  const pinnedPosts = allPosts.filter((post) => post.data.pinned && isPostVisible(post))
  return postsSort(pinnedPosts).map((post) => localizePost(post, locale))
}

// 获取最新的固定数量的文章
export async function getNumPosts(size: number, locale: Locale = 'zh-cn'): Promise<CollectionEntry<'posts'>[]> {
  const allPosts = await getCollection('posts')
  return postsSort(allPosts.filter(isPostVisible))
    .slice(0, size)
    .map((post) => localizePost(post, locale))
}

// 获取标签
export async function getAllTags(locale: Locale = 'zh-cn'): Promise<Record<string, number>> {
  const allPosts = await getAllPosts(locale)
  const tags = allPosts.flatMap((post) => post.data.tags || [])
  return tags.reduce(
    (acc, tag) => {
      acc[tag] = (acc[tag] || 0) + 1
      return acc
    },
    {} as Record<string, number>
  )
}

// 获取project
export async function getAllProjects(): Promise<CollectionEntry<'projects'>[]> {
  const allProjects = await getCollection('projects')
  return allProjects.filter((project) => !project.data.draft)
}
