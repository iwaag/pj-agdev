// Home: registered workspaces, and the setup actions (create a project,
// register an existing workspace). The actions are always shown, also when
// the registry is missing, empty or unreadable. `wfe create` and
// `wfe register` run the same operations.
import type { CreateProjectResult, Diagnostic, RegisterResponse, WorkspacesResponse } from '../shared/api.ts'
import { api } from './api.ts'
import { live } from './live.ts'
import { append, h, short } from './dom.ts'
import type { ViewHandle } from './main.ts'

export function diagnosticList(diags: Diagnostic[]): HTMLElement | null {
  if (!diags.length) return null
  return h('ul.diagnostics', diags.map(d => h(`li.${d.severity}`, h('span', d.message), d.fix ? h('span.fix', ` — ${d.fix}`) : null)))
}

export function renderHomeView(root: HTMLElement): ViewHandle {
  let data: WorkspacesResponse | null = null
  let loadError = ''
  let createResult: CreateProjectResult | null = null
  let registerResult: RegisterResponse | null = null
  let busy = false
  let disposed = false

  const header = h('header.topbar', h('div.crumbs', h('strong', 'Workflow editor'), h('span.sep', '/'), h('span.muted', 'Projects')))
  const main = h('main.project-grid.home')
  root.append(header, main)

  // Inputs outlive re-renders so nothing typed is lost.
  const f = {
    id: h('input', { placeholder: 'release-notes', 'aria-label': 'Project id' }),
    name: h('input', { placeholder: 'Release Notes', 'aria-label': 'Project name' }),
    intent: h('textarea', { rows: 3, 'aria-label': 'Project intent', placeholder: 'Why the project exists.' }),
    goals: h('textarea', { rows: 3, 'aria-label': 'Project goals', placeholder: 'One goal per line.' }),
    dir: h('input', { 'aria-label': 'Project folder' }),
    source: h('input', { 'aria-label': 'devdocs source' }),
    regPath: h('input', { 'aria-label': 'Workspace path', placeholder: 'pj-existing or an absolute path' }),
    regId: h('input', { 'aria-label': 'Workspace id', placeholder: 'from project.yaml' }),
  }
  f.id.addEventListener('input', () => { f.dir.placeholder = `pj-${f.id.value.trim() || '<id>'}`; f.source.placeholder = `new: sources/${f.id.value.trim() || '<id>'}-devdocs.git` })
  f.dir.placeholder = 'pj-<id>'
  f.source.placeholder = 'new: sources/<id>-devdocs.git'

  async function load() {
    try {
      data = await api.workspaces()
      loadError = ''
    } catch (e) {
      data = null
      loadError = (e as Error).message
    }
    if (!disposed) render()
  }

  async function create(resume = false) {
    busy = true; createResult = null; render()
    try {
      createResult = await api.createProject({
        id: f.id.value.trim(), name: f.name.value.trim(), intent: f.intent.value,
        goals: f.goals.value.split('\n').map(g => g.trim()).filter(Boolean),
        dir: f.dir.value.trim() || undefined, devdocsSource: f.source.value.trim() || undefined, resume,
      })
    } catch (e) {
      createResult = { ok: false, message: (e as Error).message, root: '', steps: [], commits: [] }
    }
    busy = false
    if (createResult.ok && createResult.workspace) { location.hash = `#/ws/${encodeURIComponent(createResult.workspace)}`; return }
    await load()
  }

  async function register() {
    busy = true; registerResult = null; render()
    try {
      registerResult = await api.register(f.regPath.value.trim(), f.regId.value.trim() || undefined)
    } catch (e) {
      registerResult = { ok: false, status: 'refused', message: (e as Error).message, diagnostics: [] }
    }
    busy = false
    if (registerResult.ok && registerResult.registration && !registerResult.diagnostics.some(d => d.severity === 'error')) {
      location.hash = `#/ws/${encodeURIComponent(registerResult.registration.id)}`
      return
    }
    await load()
  }

  function renderList(): HTMLElement {
    const card = h('section.card.workspaces', h('h2', 'Projects'))
    if (loadError) {
      card.append(h('div.banner.error', h('strong', 'The registry cannot be used: '), loadError))
      return card
    }
    if (!data) { card.append(h('p.muted', 'Loading…')); return card }
    card.append(h('p.muted.small', `Registered workspaces in ${data.registry.path}${data.registry.exists ? '' : ' (not created yet)'}. Availability is what this service observes now.`))
    if (!data.workspaces.length) card.append(h('p.muted', 'No project is registered yet. Create one, or register an existing workspace.'))
    for (const w of data.workspaces) {
      card.append(h('div.ws-row', { dataset: { id: w.id } },
        h(`span.dot.${w.observed.available ? 'on' : 'off'}`),
        h('div.ws-main', h('strong', w.observed.projectName || w.label), h('span.muted.small',
          `workspace ${w.id} · `, w.observed.available
            ? `${w.observed.branch ?? 'detached'} @ ${short(w.observed.head)}${w.observed.projectId ? ` · project ${w.observed.projectId}` : ''}${w.observed.reason ? ` · ${w.observed.reason}` : ''}`
            : `registered, not available: ${w.observed.reason}`)),
        h('a.button', { href: `#/ws/${encodeURIComponent(w.id)}`, hidden: !w.observed.available }, 'Open')))
    }
    return card
  }

  function renderCreate(): HTMLElement {
    const area = data?.area.path ?? 'the authoring area'
    const card = h('section.card.create-project', h('h2', 'Create project'),
      h('p.muted.small', `Creates a Git repository with project.yaml, .gitignore and devdocs as a submodule beneath ${area}, makes the initial commits with your Git identity, and registers it. Nothing is pushed.`),
      h('div.row', h('label.field', h('span', 'Id'), f.id), h('label.field', h('span', 'Name'), f.name)),
      h('label.field', h('span', 'Intent'), f.intent),
      h('label.field', h('span', 'Goals'), f.goals),
      h('div.row', h('label.field', h('span', 'Folder (in the area)'), f.dir), h('label.field', h('span', 'devdocs source (optional)'), f.source)),
      h('div.save-row', h('button.primary', { disabled: busy, onclick: () => void create() }, busy ? 'Working…' : 'Create project')))
    if (createResult) {
      append(card, [h(`div.banner.${createResult.ok ? 'ok' : 'error'}`, createResult.message),
        createResult.steps.length ? h('ul.steps', createResult.steps.map(s => h(`li.${s.status}`, `${s.status} · ${s.name}: ${s.detail}`))) : null,
        createResult.resumable ? h('button', { disabled: busy, onclick: () => void create(true) }, 'Continue creation') : null])
    }
    return card
  }

  function renderRegister(): HTMLElement {
    const card = h('section.card.register-workspace', h('h2', 'Register workspace'),
      h('p.muted.small', `Records an existing project's Git root in the registry. A relative path is taken from ${data?.area.path ?? 'the authoring area'}. Only the registry changes.`),
      h('div.row', h('label.field', h('span', 'Path'), f.regPath), h('label.field', h('span', 'Workspace id (optional)'), f.regId),
        h('button', { disabled: busy, onclick: () => void register() }, 'Register')))
    if (registerResult) {
      const r = registerResult
      append(card, [h(`div.banner.${r.ok ? (r.diagnostics.some(d => d.severity === 'error') ? 'warn' : 'ok') : 'error'}`, r.message,
        r.ok && r.registration ? h('a.button', { href: `#/ws/${encodeURIComponent(r.registration.id)}` }, 'Open') : null),
      diagnosticList(r.diagnostics)])
    }
    return card
  }

  function render() {
    main.replaceChildren(h('div.col', renderList(), renderRegister()), h('div.col', renderCreate()))
  }

  // The registry may change from the CLI or by hand; the list follows it.
  const stream = live(api.eventsUrl(), { classify: ev => (ev.kind === 'registry' ? ['registry'] : null), flush: () => load(), state: () => {} })

  render()
  void load()
  return { dispose: () => { disposed = true; stream.close() }, isDirty: () => false }
}
