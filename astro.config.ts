import { defineConfig } from 'astro/config'
import tailwindcss from '@tailwindcss/vite'
import react from '@astrojs/react'
import mdx from '@astrojs/mdx'
import sitemap from '@astrojs/sitemap'
import robotsTxt from 'astro-robots-txt'
import expressiveCode from 'astro-expressive-code'
import { remarkPlugins, rehypePlugins } from './plugins'
import { SITE } from './src/config'

export default defineConfig({
  site: SITE.website,
  base: SITE.base,
  i18n: {
    defaultLocale: 'zh-cn',
    locales: ['zh-cn', 'zh-hk'],
    routing: {
      prefixDefaultLocale: true,
      redirectToDefaultLocale: false,
    },
  },
  prefetch: {
    prefetchAll: true,
    defaultStrategy: 'viewport',
  },
  vite: {
    plugins: [tailwindcss()],
    build: {
      chunkSizeWarningLimit: 1500,
    },
  },
  markdown: {
    syntaxHighlight: false,
    remarkPlugins,
    rehypePlugins,
  },
  integrations: [
    expressiveCode(),
    mdx(),
    react(),
    sitemap({
      filter: (page) => {
        const pathname = new URL(page).pathname
        return pathname !== '/' && pathname !== '/photos/'
      },
      i18n: {
        defaultLocale: 'zh-cn',
        locales: {
          'zh-cn': 'zh-CN',
          'zh-hk': 'zh-HK',
        },
      },
    }),
    robotsTxt(),
  ],
})
