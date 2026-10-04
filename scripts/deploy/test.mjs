import assert from 'node:assert/strict'
import { mkdir, mkdtemp, readFile, readdir, writeFile } from 'node:fs/promises'
import { resolve, join } from 'node:path'
import { spawnSync } from 'node:child_process'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const yaml = createRequire(require.resolve('tsx/package.json'))('yaml')
const workflow = yaml.parse(await readFile('.github/workflows/blog.yml', 'utf8'))
assert.deepEqual(workflow.on.push.branches, ['main'])
assert.ok(workflow.on.pull_request.types.includes('closed'))
assert.ok(!workflow.on.pull_request_target)
assert.equal(workflow.permissions.contents, 'read')
assert.equal(workflow.jobs.build.permissions?.['id-token'], undefined)
assert.equal(workflow.jobs.production.permissions['id-token'], 'write')
assert.ok(workflow.jobs.production.if.includes("github.ref == 'refs/heads/main'"))
assert.ok(workflow.jobs.preview.if.includes('head.repo.full_name == github.repository'))
for (const job of Object.values(workflow.jobs)) {
  for (const step of job.steps) if (step.uses) assert.match(step.uses, /@[0-9a-f]{40}$/)
}

await mkdir('.astro', { recursive: true })
const fixtureRoot = await mkdtemp(resolve('.astro/deployment-tests-'))
const paths = [
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
  'pagefind/pagefind.js',
  '_astro/main.js',
  'robots.txt',
  'rss.xml',
]
const helper = resolve('scripts/deploy/prepare.mjs')
for (const mode of ['production', 'preview']) {
  const fixture = join(fixtureRoot, mode)
  for (const name of paths) {
    const path = join(fixture, 'dist', name)
    await mkdir(resolve(path, '..'), { recursive: true })
    await writeFile(path, name.endsWith('pagefind-entry.json') ? JSON.stringify({ languages: { 'zh-cn': {}, 'zh-hk': {} } }) : name)
  }
  const run = (argument) =>
    spawnSync(process.execPath, [helper, argument], {
      cwd: fixture,
      encoding: 'utf8',
      env: { ...process.env, GITHUB_SHA: 'test-sha', GITHUB_RUN_ID: 'test-run' },
    })
  assert.equal(run('check').status, 0)
  const result = run(mode)
  assert.equal(result.status, 0, result.stderr)
  const marker = JSON.parse(await readFile(join(fixture, 'dist/deployment-status.json'), 'utf8'))
  assert.equal(marker.commit, 'test-sha')
  assert.equal(marker.mode, mode)
  if (mode === 'preview') {
    const config = JSON.parse(await readFile(join(fixture, 'dist/staticwebapp.config.json'), 'utf8'))
    assert.match(config.globalHeaders['X-Robots-Tag'], /noindex/)
    assert.equal(config.responseOverrides['404'].statusCode, 404)
    assert.ok(!config.navigationFallback)
    assert.equal(await readFile(join(fixture, 'dist/robots.txt'), 'utf8'), 'User-agent: *\nDisallow: /\n')
  } else {
    const staging = join(fixture, '.astro/deployment-upload')
    assert.equal(await readFile(join(staging, 'assets/_astro/main.js'), 'utf8'), '_astro/main.js')
    assert.equal(await readFile(join(staging, 'pages/zh-cn/index.html'), 'utf8'), 'zh-cn/index.html')
    assert.equal(await readFile(join(staging, 'support/pagefind/pagefind.js'), 'utf8'), 'pagefind/pagefind.js')
    assert.equal((await readdir(join(staging, 'search/pagefind'))).length, 1)
    assert.notEqual(run(mode).status, 0, 'Reject stale staging directories')
  }
}
console.log(
  'PASS: workflow permissions, pinned actions, static checks, isolated preview settings, ordered upload batches and stale staging rejection'
)
