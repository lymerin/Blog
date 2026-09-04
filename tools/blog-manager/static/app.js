(() => {
  const root = document.documentElement
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content || ''
  const localFetch = (url, options = {}) => {
    const headers = new Headers(options.headers || {})
    headers.set('X-CSRF-Token', csrfToken)
    return fetch(url, { ...options, headers })
  }
  document.querySelectorAll('form[method="post"]').forEach((form) => {
    const token = document.createElement('input')
    token.type = 'hidden'
    token.name = 'csrf_token'
    token.value = csrfToken
    form.append(token)
  })
  const savedTheme = localStorage.getItem('blog-manager-theme')
  if (savedTheme === 'dark') root.classList.add('dark')
  document.querySelector('[data-theme-toggle]')?.addEventListener('click', () => {
    root.classList.toggle('dark')
    localStorage.setItem('blog-manager-theme', root.classList.contains('dark') ? 'dark' : 'light')
  })

  document.querySelectorAll('[data-confirm-form]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      if (!window.confirm(form.dataset.confirmForm || 'Are you sure?')) event.preventDefault()
    })
  })

  const importPanel = document.querySelector('[data-import-panel]')
  if (importPanel) {
    const input = importPanel.querySelector('[data-import-file]')
    const zone = importPanel.querySelector('[data-drop-zone]')
    const form = importPanel.querySelector('[data-import-form]')
    const message = importPanel.querySelector('[data-import-message]')
    let currentFile = null

    const showMessage = (text, kind = '') => {
      message.textContent = text
      message.className = `notice ${kind}`
    }
    const setField = (name, value) => {
      const field = form.querySelector(`[name="${name}"]`)
      if (field) field.value = value ?? ''
    }
    const inspect = async (file) => {
      currentFile = file
      const payload = new FormData()
      payload.append('file', file)
      showMessage('Inspecting Frontmatter…')
      const response = await localFetch('/api/import/inspect', { method: 'POST', body: payload })
      const result = await response.json()
      if (!result.ok) {
        showMessage(result.error, 'error')
        form.classList.add('hidden')
        return
      }
      form.classList.remove('hidden')
      form.querySelector('[data-field="filename"]').value = result.filename
      setField('title', result.metadata.title)
      setField('description', result.metadata.description)
      setField('slug', result.slug)
      setField('pubDate', String(result.metadata.pubDate || '').slice(0, 10))
      setField('tags', (result.metadata.tags || []).join(', '))
      setField('author', result.metadata.author)
      form.querySelector('[name="draft"]').checked = Boolean(result.metadata.draft)
      form.querySelector('[name="pinned"]').checked = Boolean(result.metadata.pinned)
      form.querySelector('[name="recommend"]').checked = Boolean(result.metadata.recommend)
      const details = result.errors.length ? `Frontmatter needs attention: ${result.errors.join('; ')}. Complete the form before importing.` : 'Frontmatter is valid. Review and confirm.'
      showMessage(result.conflict ? `${details} A file with this slug already exists; choose a conflict action.` : details, result.errors.length || result.conflict ? '' : 'success')
    }
    input.addEventListener('change', () => input.files[0] && inspect(input.files[0]))
    ;['dragenter', 'dragover'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.add('dragging') }))
    ;['dragleave', 'drop'].forEach((type) => zone.addEventListener(type, (event) => { event.preventDefault(); zone.classList.remove('dragging') }))
    zone.addEventListener('drop', (event) => event.dataTransfer.files[0] && inspect(event.dataTransfer.files[0]))
    form.addEventListener('submit', async (event) => {
      event.preventDefault()
      if (!currentFile) return showMessage('Choose a file first.', 'error')
      if (form.conflictAction.value === 'overwrite' && !window.confirm('Overwrite the existing article? This cannot be undone.')) return
      const payload = new FormData(form)
      if (form.conflictAction.value === 'overwrite') payload.append('overwriteConfirmed', '1')
      payload.append('file', currentFile)
      const response = await localFetch('/api/import/commit', { method: 'POST', body: payload })
      const result = await response.json()
      if (!result.ok) return showMessage(result.error, 'error')
      window.location.assign(result.redirect)
    })
  }

  const fetchButton = document.querySelector('[data-fetch-pr]')
  if (fetchButton) {
    const message = document.querySelector('[data-fetch-message]')
    const form = document.querySelector('[data-pr-form]')
    const set = (name, value) => { const field = form.querySelector(`[name="${name}"]`); if (field) field.value = value ?? '' }
    fetchButton.addEventListener('click', async () => {
      const url = document.querySelector('[data-fetch-url]').value.trim()
      message.textContent = 'Fetching…'
      const response = await localFetch('/api/github/fetch', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ url }) })
      const result = await response.json()
      if (!result.ok) { message.textContent = `${result.error} Manual entry is still available.`; return }
      if (result.project) set('project', result.project)
      set('number', result.number)
      set('url', result.url)
      set('title', result.title)
      set('mergedAt', String(result.mergedAt || '').slice(0, 16))
      set('author', result.author)
      set('issueNumber', result.issueNumber)
      set('issueUrl', result.issueUrl)
      message.textContent = result.merged ? 'Fetched. Review every field before saving.' : 'Fetched, but this PR is not merged. Enter a merged date only when appropriate.'
    })
  }

  const previewPanel = document.querySelector('[data-preview-panel]')
  if (previewPanel) {
    const output = previewPanel.querySelector('[data-process-output]')
    const state = previewPanel.querySelector('[data-preview-state]')
    const run = async (url) => {
      state.textContent = 'Working…'
      const response = await localFetch(url, { method: 'POST' })
      const result = await response.json()
      state.textContent = result.running ? 'Running' : result.success === true ? 'Success' : result.external ? 'External process' : 'Stopped'
      output.textContent = result.output || result.logs || result.error || ''
      return result
    }
    previewPanel.querySelectorAll('[data-preview-action]').forEach((button) => button.addEventListener('click', () => run(`/api/preview/${button.dataset.previewAction}`)))
    previewPanel.querySelector('[data-build]').addEventListener('click', () => run('/api/build'))
  }
})()
