import type { CollectionEntry } from 'astro:content'

export const POST_CATEGORIES = ['open-source', 'notes'] as const
export type PostCategory = (typeof POST_CATEGORIES)[number]

export function getPostCategory(post: CollectionEntry<'posts'>): PostCategory {
  return post.data.category
}
