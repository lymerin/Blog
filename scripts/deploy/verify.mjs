import assert from 'node:assert/strict'

const base = new URL(process.argv[2] || '')
if (base.protocol !== 'https:' || base.pathname !== '/') throw new Error('Expected an HTTPS site root')
const mode = process.argv[3] || 'production'
async function request(path) {
  const response = await fetch(new URL(path, base), { signal: AbortSignal.timeout(30000), cache: 'no-store' })
  assert.equal(response.status, 200, `${path}: HTTP ${response.status}`)
  return response
}
// A deployment can take a little time to become visible at the public endpoint.
let marker
for (let attempt = 0; attempt < 12; attempt++) {
  try {
    marker = await (await request(`/deployment-status.json?run=${process.env.GITHUB_RUN_ID || 'local'}`)).json()
    if (!process.env.GITHUB_SHA || marker.commit === process.env.GITHUB_SHA) break
  } catch (error) {
    if (attempt === 11) throw error
  }
  await new Promise((done) => setTimeout(done, 5000))
}
if (process.env.GITHUB_SHA) assert.equal(marker?.commit, process.env.GITHUB_SHA, 'Public site must match this workflow commit')
assert.equal(marker?.mode, mode)
const paths = [
  '/',
  '/zh-cn/',
  '/zh-hk/',
  '/zh-cn/posts/',
  '/zh-hk/posts/',
  '/zh-cn/posts/category/open-source',
  '/zh-cn/posts/category/notes',
  '/zh-hk/posts/category/open-source',
  '/zh-hk/posts/category/notes',
  '/zh-cn/open-source/',
  '/zh-hk/open-source/',
  '/404.html',
]
let postsHtml = ''
for (const path of paths) {
  const response = await request(path)
  if (mode === 'preview') assert.match(response.headers.get('x-robots-tag') || '', /noindex/)
  const html = await response.text()
  assert.match(html, /<html[\s>]/i, `${path}: must serve HTML`)
  if (path === '/zh-cn/posts/') {
    postsHtml = html
    assert.ok(html.includes('开源实践') && html.includes('技术笔记'), 'Current categories must be published')
  }
  console.log(`OK ${path}`)
}
const assets = [...new Set([...postsHtml.matchAll(/(?:src|href)="(\/_astro\/[^"?#]+)"/g)].map((match) => match[1]))]
assert.ok(assets.length > 0, 'No Astro resources found')
for (const asset of assets) await request(asset)
const article = [...postsHtml.matchAll(/href="(\/zh-cn\/posts\/[^"?#]+)"/g)]
  .map((match) => match[1])
  .find((path) => !path.startsWith('/zh-cn/posts/category/'))
if (article) await request(article)
const search = await (await request('/pagefind/pagefind-entry.json')).json()
assert.ok(search.languages?.['zh-cn'] && search.languages?.['zh-hk'], 'Both search indexes must be available')
await request('/pagefind/pagefind.js')
const missing = await fetch(new URL('/deployment-smoke-test-not-found/', base), { signal: AbortSignal.timeout(30000) })
assert.equal(missing.status, 404, 'Missing URLs must return 404, not a homepage fallback')
console.log(`Verified ${assets.length} referenced resources, an article, search entry, 404 and deployment ${marker.commit}`)
