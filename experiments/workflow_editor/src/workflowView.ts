// Placeholder until step 3.
import { h } from './dom.ts'
import type { ViewHandle } from './main.ts'

export function renderWorkflowView(root: HTMLElement, wsId: string, file: string): ViewHandle {
  root.append(h('p', `Workflow editor for ${file} in ${wsId} arrives in step 3. `, h('a', { href: `#/ws/${encodeURIComponent(wsId)}` }, 'Back to project')))
  return { dispose: () => {}, isDirty: () => false }
}
