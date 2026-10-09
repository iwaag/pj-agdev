// Hash routes: #/ws/<workspace> (project editor) and
// #/ws/<workspace>/wf/<file> (workflow editor).
import './styles.css'
import { api } from './api.ts'
import { h } from './dom.ts'
import { renderProjectView } from './projectView.ts'
import { renderWorkflowView } from './workflowView.ts'

const app = document.getElementById('app')!
let dispose: (() => void) | undefined

// A view with unsaved changes can veto navigation away from it.
export interface ViewHandle { dispose: () => void; isDirty: () => boolean }
let current: ViewHandle | undefined
let lastHash = location.hash

async function route() {
  if (current?.isDirty() && location.hash !== lastHash) {
    if (!confirm('Discard unsaved changes in this view?')) { history.replaceState(null, '', lastHash); return }
  }
  lastHash = location.hash
  dispose?.(); current = undefined
  const parts = location.hash.replace(/^#\/?/, '').split('/').filter(Boolean).map(decodeURIComponent)
  app.replaceChildren()
  if (parts[0] === 'ws' && parts[1] && parts[2] === 'wf' && parts[3]) {
    current = renderWorkflowView(app, parts[1], parts[3])
  } else if (parts[0] === 'ws' && parts[1]) {
    current = renderProjectView(app, parts[1])
  } else {
    const list = await api.workspaces().catch(e => { app.append(h('p.error', String(e.message))); return null })
    const first = list?.workspaces.find(w => w.observed.available)
    if (first) { location.replace(`#/ws/${encodeURIComponent(first.id)}`); return }
    app.append(h('p.empty', 'No registered workspace is available. Run `npm run seed -- --reset` or edit the registry.'))
  }
  dispose = current?.dispose
}

window.addEventListener('hashchange', () => void route())
window.addEventListener('beforeunload', e => { if (current?.isDirty()) e.preventDefault() })
void route()
