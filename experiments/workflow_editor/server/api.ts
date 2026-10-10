// HTTP routes of the local service. JSON in, JSON out; the UI is one client.
import type { IncomingMessage, ServerResponse } from 'node:http'
import { mkdir, readFile, stat } from 'node:fs/promises'
import { dirname, extname, isAbsolute, join, normalize, sep } from 'node:path'
import type { RepositoryStatus, WorkspaceSummary, WorkspacesResponse } from '../shared/api.ts'
import { APPROVAL_KINDS, type ApprovalKind, type Project, type Workflow } from '../shared/model.ts'
import { addNewRepository, createProject } from './create.ts'
import { BoundaryError, inside } from './files.ts'
import { loadRegistry, observe, registerWorkspace, RegistryError, type Registry } from './registry.ts'
import type { Watcher } from './watch.ts'
import { RequestError, Workspace } from './workspace.ts'

export interface ServiceConfig {
  registryFile: string
  // The authoring area: browser-created projects go beneath it and new
  // devdocs sources into its sources/. Defaults to the registry's directory.
  area?: string
  allowedOrigins: string[]
  allowedHosts: string[]
  distDir?: string // serve the built UI from the same origin
  watcher?: Watcher
}

const MAX_BODY = 2 * 1024 * 1024

function send(res: ServerResponse, status: number, body: unknown) {
  const text = JSON.stringify(body)
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' })
  res.end(text)
}

async function body(req: IncomingMessage): Promise<unknown> {
  const type = req.headers['content-type'] ?? ''
  if (!type.startsWith('application/json')) throw new RequestError(415, 'writes require content-type: application/json')
  const chunks: Buffer[] = []
  let size = 0
  for await (const chunk of req) {
    size += (chunk as Buffer).length
    if (size > MAX_BODY) throw new RequestError(413, 'request body too large')
    chunks.push(chunk as Buffer)
  }
  try { return JSON.parse(Buffer.concat(chunks).toString('utf8')) } catch { throw new RequestError(400, 'invalid JSON body') }
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

// Minimal structural check of a model sent by a client. Validation of content
// happens in shared/validate.ts; this only keeps wrong types out of the YAML.
function asWorkflow(v: unknown): Workflow {
  if (!isObj(v) || !isObj(v.repositories) || !isObj(v.nodes) || !Array.isArray(v.edges) || !isObj(v.approvals) || !isObj(v.layout) || !isObj((v.layout as Record<string, unknown>).nodes)) {
    throw new RequestError(400, 'body.workflow is not a workflow model')
  }
  for (const k of ['schema', 'id', 'name', 'intent']) if (typeof v[k] !== 'string') throw new RequestError(400, `workflow.${k} must be text`)
  for (const [id, n] of Object.entries(v.nodes)) {
    if (!isObj(n) || typeof n.type !== 'string' || typeof n.description !== 'string' || typeof n.name !== 'string' ||
      !Array.isArray(n.repositories) || !n.repositories.every(r => typeof r === 'string') ||
      (n.workflow !== undefined && typeof n.workflow !== 'string')) throw new RequestError(400, `workflow.nodes.${id} is malformed`)
  }
  for (const [k, b] of Object.entries(v.repositories)) {
    if (!isObj(b) || typeof b.path !== 'string' || typeof b.access !== 'string') throw new RequestError(400, `workflow.repositories.${k} is malformed`)
  }
  for (const e of v.edges) if (!isObj(e) || typeof e.from !== 'string' || typeof e.to !== 'string') throw new RequestError(400, 'workflow.edges is malformed')
  for (const [k, p] of Object.entries((v.layout as Record<string, Record<string, unknown>>).nodes)) {
    if (!isObj(p) || typeof p.x !== 'number' || typeof p.y !== 'number' || !Number.isFinite(p.x) || !Number.isFinite(p.y)) throw new RequestError(400, `workflow.layout.nodes.${k} is malformed`)
  }
  return v as unknown as Workflow
}

function asProject(v: unknown): Project {
  if (!isObj(v)) throw new RequestError(400, 'body.project is not a project model')
  for (const k of ['schema', 'id', 'name', 'intent']) if (typeof v[k] !== 'string') throw new RequestError(400, `project.${k} must be text`)
  if (!Array.isArray(v.goals) || !v.goals.every(g => typeof g === 'string')) throw new RequestError(400, 'project.goals must be a list of text')
  return v as unknown as Project
}

const MIME: Record<string, string> = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
  '.svg': 'image/svg+xml', '.json': 'application/json', '.ico': 'image/x-icon', '.png': 'image/png',
}

export function createHandler(config: ServiceConfig) {
  async function registry(): Promise<Registry> { return loadRegistry(config.registryFile) }
  const area = config.area ?? dirname(config.registryFile)
  const texts = (v: unknown) => Array.isArray(v) && v.every(x => typeof x === 'string')

  async function workspace(id: string): Promise<Workspace> {
    const reg = (await registry()).workspaces.find(w => w.id === id)
    if (!reg) throw new RequestError(404, `workspace "${id}" is not registered`)
    const obs = await observe(reg)
    if (!obs.available) throw new RequestError(409, `workspace "${id}" is registered but not available: ${obs.reason}`)
    return new Workspace(reg)
  }

  // Repository inspection costs several Git commands per submodule. While a
  // watcher observes a workspace, its result is reused until the Git
  // fingerprint or .gitmodules changes; `?refresh=1` always inspects anew.
  const repoCache = new Map<string, { key: string; repos: RepositoryStatus[] }>()
  async function withRepositories(ws: Workspace, refresh: boolean) {
    const gitKey = config.watcher?.gitKey(ws.reg.id)
    if (!gitKey) return
    const modules = await readFile(join(ws.root, '.gitmodules'), 'utf8').catch(() => '')
    const key = `${gitKey}\0${modules}`
    const hit = repoCache.get(ws.reg.id)
    if (hit && hit.key === key && !refresh) { ws.knownRepositories = hit.repos; return }
    const repos = await ws.repositories()
    repoCache.set(ws.reg.id, { key, repos })
    ws.knownRepositories = repos
  }

  async function serveStatic(res: ServerResponse, url: URL): Promise<boolean> {
    if (!config.distDir) return false
    const rel = normalize(decodeURIComponent(url.pathname)).replace(/^([/\\])+/, '')
    let file = join(config.distDir, rel)
    if (!file.startsWith(config.distDir + sep) && file !== config.distDir) return false
    const st = await stat(file).catch(() => null)
    if (!st || st.isDirectory()) file = join(config.distDir, 'index.html')
    const data = await readFile(file).catch(() => null)
    if (!data) return false
    res.writeHead(200, { 'content-type': MIME[extname(file)] ?? 'application/octet-stream' })
    res.end(data)
    return true
  }

  return async function handle(req: IncomingMessage, res: ServerResponse) {
    try {
      // Only answer to local host names (DNS-rebinding guard).
      const host = (req.headers.host ?? '').replace(/:\d+$/, '')
      if (!config.allowedHosts.includes(host)) throw new RequestError(403, `host "${host}" is not allowed`)
      const url = new URL(req.url ?? '/', 'http://local')
      const method = req.method ?? 'GET'
      // Browser writes only from the editor's configured origin. Clients that
      // send no Origin (curl, tests) are local processes and are allowed.
      if (method !== 'GET' && method !== 'HEAD') {
        const origin = req.headers.origin
        if (origin !== undefined && !config.allowedOrigins.includes(origin)) throw new RequestError(403, `origin "${origin}" may not write`)
      }
      const parts = url.pathname.split('/').filter(Boolean).map(decodeURIComponent)
      if (parts[0] !== 'api') {
        if (method === 'GET' && await serveStatic(res, url)) return
        if (method === 'GET' && !config.distDir && url.pathname === '/') {
          res.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' })
          res.end('This is the workflow editor API only.\nOpen the UI through the Vite dev server (npm run dev → http://127.0.0.1:5175),\nor run `npm start` to serve the built UI here.\n')
          return
        }
        throw new RequestError(404, 'not found')
      }
      const [, a, wsId, b, file, action] = parts

      // The home page's stream: registry changes only.
      if (a === 'events' && method === 'GET') {
        if (!config.watcher) throw new RequestError(404, 'watching is disabled')
        return await config.watcher.stream(undefined, req, res)
      }

      if (a === 'workspaces' && !wsId && method === 'GET') {
        const reg = await registry()
        const list: WorkspaceSummary[] = await Promise.all(reg.workspaces.map(async w => {
          const o = await observe(w)
          return { id: w.id, label: w.label, host: w.host, observed: { available: o.available, reason: o.reason, projectId: o.projectId, projectName: o.projectName, branch: o.branch, head: o.head } }
        }))
        const out: WorkspacesResponse = { approver: reg.approver, workspaces: list, registry: { path: config.registryFile, exists: reg.exists }, area: { path: area, sources: join(area, 'sources') } }
        return send(res, 200, out)
      }
      // Registration writes only the registry. A relative path is taken from the authoring area.
      if (a === 'workspaces' && !wsId && method === 'POST') {
        const input = await body(req) as Record<string, unknown>
        if (typeof input.path !== 'string' || !input.path.trim()) throw new RequestError(400, 'path is required')
        const id = typeof input.id === 'string' && input.id.trim() ? input.id.trim() : undefined
        const path = input.path.trim()
        const result = await registerWorkspace(config.registryFile, isAbsolute(path) ? path : join(area, path), { id })
        return send(res, result.ok ? 200 : 422, result)
      }
      // Creation writes only beneath the authoring area (the CLI takes any destination).
      if (a === 'projects' && !wsId && method === 'POST') {
        const input = await body(req) as Record<string, unknown>
        for (const k of ['id', 'name']) if (typeof input[k] !== 'string') throw new RequestError(400, `${k} is required`)
        if (input.goals !== undefined && !texts(input.goals)) throw new RequestError(400, 'goals must be a list of text')
        await mkdir(area, { recursive: true })
        const rel = typeof input.dir === 'string' && input.dir.trim() ? input.dir.trim() : `pj-${input.id}`
        const dir = await inside(area, rel)
        const result = await createProject({
          dir, id: String(input.id).trim(), name: String(input.name), intent: typeof input.intent === 'string' ? input.intent : '',
          goals: (input.goals as string[] | undefined) ?? [], sourcesDir: join(area, 'sources'),
          devdocsSource: typeof input.devdocsSource === 'string' && input.devdocsSource.trim() ? input.devdocsSource.trim() : undefined,
          registryFile: config.registryFile, resume: input.resume === true,
        })
        return send(res, result.ok ? 201 : 422, result)
      }
      if (a !== 'workspaces' || !wsId) throw new RequestError(404, 'not found')

      if (b === 'events' && method === 'GET') {
        if (!config.watcher) throw new RequestError(404, 'watching is disabled')
        const ws = await workspace(wsId)
        return await config.watcher.stream(ws, req, res)
      }

      const ws = await workspace(wsId)
      if (method === 'GET') await withRepositories(ws, url.searchParams.get('refresh') === '1')
      if (b === 'project' && !file) {
        if (method === 'GET') return send(res, 200, await ws.projectResponse())
        if (method === 'PUT') {
          const input = await body(req) as Record<string, unknown>
          const saved = await ws.saveProject(asProject(input.project))
          config.watcher?.noteOwnWrite(ws, 'project.yaml', saved.rev)
          return send(res, 200, { ok: true, ...saved })
        }
      }
      if (b === 'submodules' && !file && method === 'POST') {
        const input = await body(req) as Record<string, unknown>
        if (typeof input.path !== 'string') throw new RequestError(400, 'path is required')
        if (input.create === true) {
          const result = await addNewRepository(ws, input.path, join(area, 'sources'))
          return send(res, result.ok ? 200 : 422, result)
        }
        if (typeof input.url !== 'string') throw new RequestError(400, 'url is required (or create: true for a new local repository)')
        const result = await ws.addSubmodule(input.path, input.url)
        return send(res, result.ok ? 200 : 422, result)
      }
      if (b === 'workflows' && !file) {
        if (method === 'GET') return send(res, 200, (await ws.workflowSummaries()).list)
        if (method === 'POST') {
          const input = await body(req) as Record<string, unknown>
          if (typeof input.id !== 'string') throw new RequestError(400, 'id is required')
          return send(res, 201, await ws.createWorkflow(input.id, typeof input.name === 'string' ? input.name : ''))
        }
      }
      if (b === 'workflows' && file && !action) {
        if (method === 'GET') return send(res, 200, await ws.workflowResponse(file))
        if (method === 'PUT') {
          const input = await body(req) as Record<string, unknown>
          const saved = await ws.saveWorkflow(file, asWorkflow(input.workflow))
          config.watcher?.noteOwnWrite(ws, `devdocs/workflows/${file}`, saved.rev)
          return send(res, 200, { ok: true, ...saved })
        }
      }
      if (b === 'workflows' && file && action === 'approve' && method === 'POST') {
        const input = await body(req) as Record<string, unknown>
        if (!(APPROVAL_KINDS as readonly string[]).includes(input.kind as string)) throw new RequestError(400, 'kind must be intent or definition')
        const result = await ws.approve(file, input.kind as ApprovalKind, typeof input.approver === 'string' ? input.approver : '')
        config.watcher?.noteOwnWrite(ws, `devdocs/workflows/${file}`, result.rev)
        return send(res, 200, { ok: true, ...result })
      }
      throw new RequestError(404, `no route for ${method} ${url.pathname}`)
    } catch (e) {
      if (res.headersSent) { res.end(); return }
      if (e instanceof RequestError) return send(res, e.status, { error: e.message, detail: e.detail })
      if (e instanceof BoundaryError) return send(res, 400, { error: e.message })
      if (e instanceof RegistryError) return send(res, 500, { error: e.message })
      const err = e as NodeJS.ErrnoException
      // File system failures (permissions, disk) are reported, not hidden.
      if (err.code) return send(res, 500, { error: `${err.code}: ${err.message}` })
      console.error(e)
      return send(res, 500, { error: String((e as Error).message ?? e) })
    }
  }
}
