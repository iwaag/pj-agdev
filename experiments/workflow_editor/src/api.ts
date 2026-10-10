// Thin client for the local service. Errors carry the service's message.
import type {
  AddSubmoduleResponse, CreateProjectResult, ProjectResponse, RegisterResponse, SaveResponse, WorkflowResponse, WorkspacesResponse,
} from '../shared/api.ts'
import type { ApprovalState } from '../shared/canonical.ts'
import type { ApprovalKind, Project, Workflow } from '../shared/model.ts'

export class ApiError extends Error {
  status: number
  detail?: unknown
  constructor(status: number, message: string, detail?: unknown) { super(message); this.status = status; this.detail = detail }
}

async function call<T>(method: string, path: string, body?: unknown, okStatuses: number[] = []): Promise<T> {
  let res: Response
  try {
    res = await fetch(path, {
      method,
      headers: body === undefined ? {} : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (e) {
    throw new ApiError(0, `The editor service is not reachable (${(e as Error).message}).`)
  }
  const data = await res.json().catch(() => ({ error: `HTTP ${res.status}` }))
  if (!res.ok && !okStatuses.includes(res.status)) throw new ApiError(res.status, (data as { error?: string }).error ?? `HTTP ${res.status}`, (data as { detail?: unknown }).detail)
  return data as T
}

const ws = (id: string) => `/api/workspaces/${encodeURIComponent(id)}`
const wf = (id: string, file: string) => `${ws(id)}/workflows/${encodeURIComponent(file)}`

export const api = {
  workspaces: () => call<WorkspacesResponse>('GET', '/api/workspaces'),
  createProject: (input: { id: string; name: string; intent: string; goals: string[]; dir?: string; devdocsSource?: string; resume?: boolean }) =>
    call<CreateProjectResult>('POST', '/api/projects', input, [422]),
  register: (path: string, id?: string) => call<RegisterResponse>('POST', '/api/workspaces', { path, id }, [422]),
  project: (id: string) => call<ProjectResponse>('GET', `${ws(id)}/project`),
  saveProject: (id: string, project: Project) => call<SaveResponse>('PUT', `${ws(id)}/project`, { project }),
  addSubmodule: (id: string, path: string, url: string) => call<AddSubmoduleResponse>('POST', `${ws(id)}/submodules`, { path, url }, [422]),
  createWorkflow: (id: string, wid: string, name: string) => call<{ file: string }>('POST', `${ws(id)}/workflows`, { id: wid, name }),
  workflow: (id: string, file: string) => call<WorkflowResponse>('GET', wf(id, file)),
  saveWorkflow: (id: string, file: string, workflow: Workflow) => call<SaveResponse>('PUT', wf(id, file), { workflow }),
  approve: (id: string, file: string, kind: ApprovalKind, approver: string) =>
    call<SaveResponse & { state: ApprovalState }>('POST', `${wf(id, file)}/approve`, { kind, approver }),
  events: (id: string) => new EventSource(`${ws(id)}/events`),
}
