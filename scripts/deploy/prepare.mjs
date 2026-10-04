import { copyFile, mkdir, readFile, readdir, writeFile } from 'node:fs/promises'
import { join, resolve } from 'node:path'

const mode = process.argv[2]
if (!['check', 'preview', 'production'].includes(mode)) throw new Error('Expected check, preview or production')
const dist = resolve('dist')
for (const name of [
  'index.html',
  '404.html',
  'zh-cn/index.html',
  'zh-hk/index.html',
  'zh-cn/posts/index.html',
  'zh-hk/posts/index.html',
  'zh-cn/posts/category/open-source/index.html',
  'zh-cn/posts/category/notes/index.html',
  'zh-hk/posts/category/open-source/index.html',
  'zh-hk/posts/category/notes/index.html',
  'pagefind/pagefind-entry.json',
]) {
  await readFile(join(dist, name))
}
const entries = JSON.parse(await readFile(join(dist, 'pagefind/pagefind-entry.json'), 'utf8'))
if (!entries.languages?.['zh-cn'] || !entries.languages?.['zh-hk']) throw new Error('Both search languages are required')
if (mode === 'check') {
  console.log('Static routes and both search indexes verified')
  process.exit(0)
}

await writeFile(
  join(dist, 'deployment-status.json'),
  JSON.stringify(
    {
      commit: process.env.GITHUB_SHA || 'local',
      sourceCommit: process.env.SOURCE_SHA || process.env.GITHUB_SHA || 'local',
      runId: process.env.GITHUB_RUN_ID || 'local',
      deployedAt: new Date().toISOString(),
      mode,
    },
    null,
    2
  )
)

if (mode === 'preview') {
  await writeFile(join(dist, 'robots.txt'), 'User-agent: *\nDisallow: /\n')
  await writeFile(
    join(dist, 'staticwebapp.config.json'),
    JSON.stringify(
      {
        globalHeaders: { 'X-Robots-Tag': 'noindex, nofollow', 'Cache-Control': 'no-cache' },
        responseOverrides: { 404: { rewrite: '/404.html', statusCode: 404 } },
        mimeTypes: {
          '.wasm': 'application/wasm',
          '.pf_meta': 'application/octet-stream',
          '.pf_index': 'application/octet-stream',
          '.pf_fragment': 'application/octet-stream',
        },
      },
      null,
      2
    )
  )
  console.log('Preview prepared: public URL, indexing discouraged, no SPA fallback')
} else {
  // Keep each batch rooted at its own directory so paths in $web never gain a dist/ prefix.
  const uploadRoot = resolve('.astro/deployment-upload')
  const counts = { assets: 0, support: 0, pages: 0, search: 0 }
  async function stage(directory, prefix = '') {
    for (const entry of await readdir(directory, { withFileTypes: true })) {
      const name = prefix ? `${prefix}/${entry.name}` : entry.name
      if (entry.isDirectory()) await stage(join(directory, entry.name), name)
      else if (entry.isFile()) {
        const group =
          name === 'pagefind/pagefind-entry.json'
            ? 'search'
            : name.startsWith('_astro/')
              ? 'assets'
              : /\.(html|xml)$/.test(name) || ['robots.txt', 'deployment-status.json'].includes(name)
                ? 'pages'
                : 'support'
        const destination = join(uploadRoot, group, name)
        await mkdir(resolve(destination, '..'), { recursive: true })
        await copyFile(join(directory, entry.name), destination)
        counts[group]++
      } else throw new Error(`Unsupported output entry: ${name}`)
    }
  }
  // CI uses a fresh checkout. Refuse to reuse stale staging files on manual runs.
  await mkdir(resolve(uploadRoot, '..'), { recursive: true })
  try {
    await mkdir(uploadRoot)
  } catch (error) {
    if (error.code === 'EEXIST') throw new Error('Staging already exists; use a fresh checkout for deployment')
    throw error
  }
  await stage(dist)
  console.log('Production batches prepared:', counts)
}
