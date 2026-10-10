// Workflow runs on disk (docs/runs.md): creation with the definition
// snapshot, reading and checking records, and operations that append one
// history entry in one atomic replacement of run.json. The rules are in
// shared/run.ts; this module only reads and writes files. The CLI and the
// service both call it.
import { createHash } from 'node:crypto'
import { mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import type { FileProblem, RelatedRun, RunFile, RunResponse, RunSummary, SourceComparison } from '../shared/api.ts'
import { approvalStates, semanticDigest } from '../shared/canonical.ts'
import { ID_PATTERN, normalizeRepoPath, type Workflow } from '../shared/model.ts'
import {
  checkRecord, operate, RUN_ID, RunError, runKey, validRunRef,
  type BundleEntry, type DefinitionRef, type EntrustRef, type Executor, type OpInput, type RepoContext, type RunGraph,
  type RunInput, type RunRecord, type RunRef,
} from '../shared/run.ts'
import { atomicWrite, inside, readTextOrNull } from './files.ts'
import { git } from './git.ts'
import { RequestError, WORKFLOWS_DIR, type Workspace } from './workspace.ts'
import { parseWorkflow } from './yamlDoc.ts'

export const RUN_FILE = 'run.json'
export const DEFINITION_DIR = 'definition'
const MAX_RUNS = 500
const MAX_FILES = 200
const MAX_READ = 1024 * 1024

export const runDir = (r: RunRef) => `devdocs/${r.workflow}/runs/${r.run}`
const sha256 = (text: string | Buffer) => createHash('sha256').update(text).digest('hex')
const sigOf = async (path: string) => { const s = await stat(path).catch(() => null); return s ? `${s.size}:${s.mtimeMs}:${s.ino}` : null }

export function graphOf(w: Workflow): RunGraph {
  return {
    nodes: Object.fromEntries(Object.entries(w.nodes).map(([id, n]) => [id, n.workflow ? { type: n.type, workflow: n.workflow } : { type: n.type }])),
    edges: w.edges.map(e => ({ from: e.from, to: e.to })),
  }
}

// A record that cannot be used: shown, never rewritten.
export class RunProblem extends Error {
  problem: FileProblem & { code?: string }
  constructor(problem: FileProblem & { code?: string }) { super(problem.message); this.problem = problem }
}

// ---- reading ---------------------------------------------------------------------

// Reads files of one run from the working tree, or from a devdocs commit.
interface Source {
  text(rel: string): Promise<string | null> // run-relative
  list(): Promise<RunFile[]>
}

function fsSource(dir: string): Source {
  return {
    text: rel => readTextOrNull(join(dir, rel)),
    async list() {
      const names = (await readdir(dir).catch(() => [] as string[])).filter(n => !n.startsWith('.')).sort().slice(0, MAX_FILES)
      const out: RunFile[] = []
      for (const name of names) {
        const s = await stat(join(dir, name)).catch(() => null)
        if (s?.isFile()) out.push({ name, size: s.size, modified: new Date(s.mtimeMs).toISOString() })
      }
      return out
    },
  }
}

function gitSource(devdocs: string, rev: string, rel: string): Source {
  return {
    async text(f) {
      const r = await git(devdocs, ['show', `${rev}:${rel}/${f}`])
      return r.code === 0 ? r.stdout : null
    },
    async list() {
      const r = await git(devdocs, ['ls-tree', '-l', rev, '--', `${rel}/`])
      return r.stdout.split('\n').filter(l => /^\d+ blob /.test(l)).map(l => {
        const [meta, path] = l.split('\t')
        return { name: path.split('/').pop()!, size: Number(meta.trim().split(/\s+/)[3]), modified: '' }
      })
    },
  }
}

interface Bundle { entries: Record<string, { file: string; text?: string; workflow?: Workflow; problem?: string }>; graph?: RunGraph; problem?: string }

async function loadBundle(src: Source, def: unknown): Promise<Bundle> {
  const out: Bundle = { entries: {} }
  const d = def as DefinitionRef | undefined
  if (!d || typeof d !== 'object' || typeof d.root !== 'string' || typeof d.workflows !== 'object' || d.workflows === null) {
    out.problem = 'run.json has no definition reference'
    return out
  }
  for (const [id, entry] of Object.entries(d.workflows)) {
    const file = typeof entry?.file === 'string' ? entry.file : `${DEFINITION_DIR}/${id}.yaml`
    if (!file.startsWith(`${DEFINITION_DIR}/`) || file.includes('..')) { out.entries[id] = { file, problem: `bundle file "${file}" is outside ${DEFINITION_DIR}/` }; continue }
    const text = await src.text(file)
    if (text === null) { out.entries[id] = { file, problem: `${file} is missing` }; continue }
    if (sha256(text) !== entry.sha256) { out.entries[id] = { file, text, problem: `${file} differs from its recorded sha256 (the bundle was changed)` }; continue }
    const parsed = parseWorkflow(text)
    if (!parsed.ok) { out.entries[id] = { file, text, problem: `${file}: ${parsed.problem.message}` }; continue }
    if (parsed.model.id !== id) { out.entries[id] = { file, text, problem: `${file} holds workflow "${parsed.model.id}", not "${id}"` }; continue }
    out.entries[id] = { file, text, workflow: parsed.model }
  }
  const root = out.entries[d.root]
  if (!root) out.problem = `the root workflow "${d.root}" is not in the bundle`
  else if (root.problem) out.problem = root.problem
  else {
    out.graph = graphOf(root.workflow!)
    const broken = Object.entries(out.entries).find(([, e]) => e.problem)
    if (broken) out.problem = broken[1].problem
  }
  return out
}

interface Reading { text: string | null; record?: RunRecord; problem?: FileProblem & { code?: string }; bundle: Bundle; files?: RunFile[] }

// Parses and checks one run. Cached on the stat of run.json and the bundle.
const cache = new Map<string, { key: string; reading: Reading }>()

async function readFrom(src: Source, expect: RunRef, cacheKey?: string): Promise<Reading> {
  if (cacheKey) {
    const hit = cache.get(cacheKey.split('\0')[0])
    if (hit && hit.key === cacheKey) return { ...hit.reading, record: hit.reading.record && structuredClone(hit.reading.record) }
  }
  const text = await src.text(RUN_FILE)
  const reading = await (async (): Promise<Reading> => {
    if (text === null) return { text, problem: { kind: 'missing', message: `${RUN_FILE} does not exist`, code: 'missing' }, bundle: { entries: {} } }
    let raw: unknown
    try { raw = JSON.parse(text) } catch (e) { return { text, problem: { kind: 'malformed', message: `${RUN_FILE} is not valid JSON: ${(e as Error).message}`, code: 'malformed' }, bundle: { entries: {} } } }
    const r = raw as Record<string, unknown>
    const bundle = await loadBundle(src, r?.definition)
    if (bundle.problem || !bundle.graph) return { text, problem: { kind: 'shape', message: bundle.problem ?? 'no graph', code: 'bundle' }, bundle }
    const checked = checkRecord(raw, bundle.graph)
    if (!checked.ok) return { text, problem: { kind: 'shape', message: checked.message, code: checked.code }, bundle }
    if (checked.record.workflow !== expect.workflow || checked.record.run !== expect.run) {
      return { text, problem: { kind: 'shape', message: `${RUN_FILE} names ${checked.record.workflow}/${checked.record.run}, but it is stored as ${runKey(expect)}`, code: 'location' }, bundle }
    }
    return { text, record: checked.record, bundle }
  })()
  if (cacheKey) {
    if (cache.size > 2000) cache.clear()
    cache.set(cacheKey.split('\0')[0], { key: cacheKey, reading: { ...reading, record: reading.record && structuredClone(reading.record) } })
  }
  return reading
}

async function bundleSigs(dir: string): Promise<string> {
  const defDir = join(dir, DEFINITION_DIR)
  const names = (await readdir(defDir).catch(() => [] as string[])).sort()
  const sigs = await Promise.all(names.map(async n => `${n}:${await sigOf(join(defDir, n))}`))
  return sigs.join(',')
}

export async function readRun(ws: Workspace, ref: RunRef): Promise<Reading & { dir: string }> {
  const rel = runDir(ref)
  const dir = await inside(ws.root, rel)
  const key = `${dir}\0${await sigOf(join(dir, RUN_FILE))}\0${await bundleSigs(dir)}`
  return { ...(await readFrom(fsSource(dir), ref, key)), dir }
}

// Throws RequestError when the run cannot be operated on.
async function usableRun(ws: Workspace, ref: RunRef): Promise<{ record: RunRecord; graph: RunGraph; dir: string; bundle: Bundle }> {
  const r = await readRun(ws, ref)
  if (r.problem?.code === 'missing') {
    const exists = await stat(r.dir).then(() => true, () => false)
    throw new RequestError(404, exists ? `run ${runKey(ref)} has no ${RUN_FILE}` : `run ${runKey(ref)} does not exist`)
  }
  if (!r.record || !r.bundle.graph) throw new RequestError(409, `run ${runKey(ref)} cannot be used: ${r.problem?.message}. Nothing was changed; fix or restore the files (wfe run check).`, r.problem)
  return { record: r.record, graph: r.bundle.graph, dir: r.dir, bundle: r.bundle }
}

// ---- listing ---------------------------------------------------------------------

export async function runRefs(ws: Workspace, workflow?: string): Promise<RunRef[]> {
  const devdocs = await inside(ws.root, 'devdocs')
  const workflows = workflow ? [workflow] : (await readdir(devdocs, { withFileTypes: true }).catch(() => [])).filter(d => d.isDirectory() && ID_PATTERN.test(d.name)).map(d => d.name).sort()
  const out: RunRef[] = []
  for (const wf of workflows) {
    const names = (await readdir(join(devdocs, wf, 'runs'), { withFileTypes: true }).catch(() => [])).filter(d => d.isDirectory() && RUN_ID.test(d.name)).map(d => d.name).sort()
    for (const run of names) { out.push({ workflow: wf, run }); if (out.length >= MAX_RUNS) return out }
  }
  return out
}

export function summaryOf(ref: RunRef, reading: Pick<Reading, 'record' | 'problem'>): RunSummary {
  const base: RunSummary = { ref: runKey(ref), workflow: ref.workflow, run: ref.run, dir: runDir(ref) }
  const r = reading.record
  if (!r) return { ...base, problem: reading.problem }
  return {
    ...base, created: r.created, updated: r.updated, seq: r.seq, execution: r.execution.state, counts: r.execution.counts,
    waiting: r.execution.waiting.map(w => ({ node: w.node, holder: holderText(r, w.node) })), ready: r.execution.ready, failed: r.execution.failed,
    input: r.input.kind, executor: r.executor.name, parent: r.parent ? `${runKey(r.parent)} (node ${r.parent.node})` : undefined,
    decision: r.decisions.at(-1)?.decision,
  }
}

function holderText(r: RunRecord, node: string): string {
  const w = r.nodes[node]?.wait
  if (!w) return ''
  if ('question' in w.on) {
    const q = r.questions[w.on.question]
    if (q && q.answers.length && !q.takenUp && !q.withdrawn) return `${r.executor.name} (answer recorded, not yet taken up)`
  }
  return w.holder
}

export async function listRuns(ws: Workspace, workflow?: string): Promise<RunSummary[]> {
  const refs = await runRefs(ws, workflow)
  return Promise.all(refs.map(async ref => summaryOf(ref, await readRun(ws, ref))))
}

// "<workflow>/<run>", or a run id that is unique in the project.
export async function resolveRef(ws: Workspace, text: string): Promise<RunRef> {
  const parts = text.replace(/^devdocs\//, '').replace(/\/$/, '').split('/')
  if (parts.length === 3 && parts[1] === 'runs') return validRef({ workflow: parts[0], run: parts[2] })
  if (parts.length === 2) return validRef({ workflow: parts[0], run: parts[1] })
  if (parts.length === 1) {
    const hits = (await runRefs(ws)).filter(r => r.run === parts[0])
    if (hits.length === 1) return hits[0]
    if (!hits.length) throw new RequestError(404, `no run "${text}" in this project (see: wfe run list)`)
    throw new RequestError(409, `run "${text}" exists for several workflows (${hits.map(runKey).join(', ')}); use <workflow>/<run>`)
  }
  throw new RequestError(400, `"${text}" is not a run reference; use <workflow>/<run>`)
}

function validRef(r: RunRef): RunRef {
  if (!ID_PATTERN.test(r.workflow)) throw new RequestError(400, `workflow id "${r.workflow}" is invalid`)
  if (!RUN_ID.test(r.run)) throw new RequestError(400, `run id "${r.run}" must match ${RUN_ID.source}`)
  return r
}

// ---- the full view of one run ----------------------------------------------------

async function related(ws: Workspace, ref: RunRef): Promise<RelatedRun> {
  try {
    const r = await readRun(ws, ref)
    if (r.record) return { ref: runKey(ref), execution: r.record.execution.state, seq: r.record.seq }
    return { ref: runKey(ref), problem: r.problem?.code === 'missing' ? 'missing' : `${r.problem?.code ?? 'unreadable'}: ${r.problem?.message}` }
  } catch (e) {
    return { ref: runKey(ref), problem: (e as Error).message }
  }
}

// The current source of each bundled workflow, found by id: same bytes,
// changed, or gone; and whether it now lives in another file.
async function compareSources(ws: Workspace, bundle: Bundle, def: DefinitionRef | undefined): Promise<SourceComparison[]> {
  const { list } = await ws.workflowSummaries()
  const out: SourceComparison[] = []
  for (const [id, e] of Object.entries(bundle.entries)) {
    const source = def?.workflows[id]?.source
    if (!e.text) { out.push({ workflow: id, status: 'unreadable', source, detail: e.problem }); continue }
    const hit = list.find(s => s.id === id)
    if (!hit) { out.push({ workflow: id, status: 'deleted', source, detail: `no workflow "${id}" in ${WORKFLOWS_DIR} now` }); continue }
    const current = await ws.readWorkflowFile(hit.file)
    const file = `${WORKFLOWS_DIR}/${hit.file}`
    out.push({ workflow: id, status: current.text === e.text ? 'same' : 'changed', source, file, renamed: !!source && source.startsWith(`${WORKFLOWS_DIR}/`) && source !== file })
  }
  return out
}

export async function runResponse(ws: Workspace, ref: RunRef, opts: { rev?: string } = {}): Promise<RunResponse> {
  const rel = runDir(ref)
  let reading: Reading
  let revInfo: RunResponse['revInfo']
  if (opts.rev) {
    const devdocs = await inside(ws.root, 'devdocs')
    const info = await git(devdocs, ['log', '-1', '--format=%H%x00%s%x00%cI', opts.rev, '--'])
    if (info.code !== 0 || !info.stdout.trim()) throw new RequestError(404, `"${opts.rev}" is not a commit of devdocs`)
    const [commit, subject, date] = info.stdout.trim().split('\0')
    revInfo = { commit, subject, date }
    const src = gitSource(devdocs, commit, `${ref.workflow}/runs/${ref.run}`)
    reading = { ...(await readFrom(src, ref)), files: await src.list() }
  } else {
    const r = await readRun(ws, ref)
    reading = { ...r, files: await fsSource(r.dir).list() }
  }
  const record = reading.record
  const children: RelatedRun[] = []
  const artifacts: RunResponse['artifacts'] = []
  let parent: RelatedRun | undefined, predecessor: RelatedRun | undefined
  if (record && !opts.rev) {
    for (const [node, n] of Object.entries(record.nodes)) for (const c of n.children) children.push({ ...(await related(ws, c)), node })
    if (record.parent) {
      const p = await readRun(ws, record.parent)
      const links = !!p.record?.nodes[record.parent.node]?.children.some(c => c.workflow === ref.workflow && c.run === ref.run)
      parent = { ref: runKey(record.parent), node: record.parent.node, execution: p.record?.execution.state, seq: p.record?.seq, linksBack: links, problem: p.record ? undefined : p.problem?.code === 'missing' ? 'missing' : p.problem?.message }
    }
    if (record.predecessor) predecessor = await related(ws, record.predecessor)
    const seen = new Set<string>()
    for (const a of record.artifacts) {
      if (seen.has(a.path)) continue
      seen.add(a.path)
      const abs = await inside(ws.root, a.path).catch(() => null)
      artifacts.push({ path: a.path, exists: !!abs && await stat(abs).then(() => true, () => false) })
    }
  }
  return {
    workspace: ws.reg.id, ref: runKey(ref), dir: rel, rev: revInfo?.commit, revInfo,
    record, problem: reading.problem,
    bundle: Object.fromEntries(Object.entries(reading.bundle.entries).map(([id, e]) => [id, { file: e.file, workflow: e.workflow, problem: e.problem }])),
    sources: opts.rev ? [] : await compareSources(ws, reading.bundle, record?.definition),
    files: reading.files ?? [], parent, children, predecessor, artifacts,
  }
}

// A top-level file of the run folder, or an artifact the run records. Text only.
export async function readRunFile(ws: Workspace, ref: RunRef, path: string, opts: { rev?: string } = {}): Promise<{ path: string; text: string }> {
  const rel = runDir(ref)
  const r = opts.rev ? await runResponse(ws, ref, opts) : await readRun(ws, ref)
  const own = !path.includes('/') && path !== RUN_FILE && path !== '.' && path !== '..' ? `${rel}/${path}` : null
  const normalized = normalizeRepoPath(path)
  const recorded = r.record?.artifacts.some(a => a.path === normalized) ? normalized : null
  const target = own ?? recorded
  if (!target) throw new RequestError(404, `"${path}" is neither a file of ${runKey(ref)} nor an artifact it records`)
  if (opts.rev) {
    // Only devdocs content belongs to this commit. Never fall back to a
    // working-tree artifact, including files in another repository.
    if (!target.startsWith('devdocs/')) throw new RequestError(404, `${target} is outside the devdocs commit; open the current run to read it`)
    const devdocs = await inside(ws.root, 'devdocs')
    const object = `${(r as RunResponse).rev}:${target.slice('devdocs/'.length)}`
    const type = await git(devdocs, ['cat-file', '-t', object])
    if (type.code !== 0 || type.stdout.trim() !== 'blob') throw new RequestError(404, `${target} does not exist as a file in this commit`)
    const size = await git(devdocs, ['cat-file', '-s', object])
    if (size.code !== 0) throw new RequestError(404, `${target} could not be read from this commit`)
    if (Number(size.stdout.trim()) > MAX_READ) throw new RequestError(413, `${target} is larger than ${MAX_READ} bytes; open it in Git`)
    const content = await git(devdocs, ['show', object])
    if (content.code !== 0) throw new RequestError(404, `${target} could not be read from this commit`)
    return { path: target, text: content.stdout }
  }
  const abs = await inside(ws.root, target)
  const s = await stat(abs).catch(() => null)
  if (!s?.isFile()) throw new RequestError(404, `${target} does not exist`)
  if (s.size > MAX_READ) throw new RequestError(413, `${target} is larger than ${MAX_READ} bytes; open it in the editor`)
  return { path: target, text: await readFile(abs, 'utf8') }
}

// ---- creation --------------------------------------------------------------------

export interface CreateRunOptions {
  workflow: string // id or file name in devdocs/workflows
  name?: string // run id; default the next run-NNN
  input:
    | { kind: 'braindump'; text: string; author: string; recordedBy?: string }
    | { kind: 'request'; text: string; requester: string; entrustedBy: EntrustRef; onBehalfOf?: string; original?: string }
  executor: Executor
  plan?: string
  predecessor?: RunRef
  by: string
  via: string
  now?: Date
}

export interface CreatedRun { ref: RunRef; dir: string; record: RunRecord; files: string[] }

async function nextRunId(ws: Workspace, workflow: string): Promise<string> {
  const used = (await runRefs(ws, workflow)).map(r => /^run-(\d+)$/.exec(r.run)?.[1]).filter((n): n is string => !!n).map(Number)
  return `run-${String((used.length ? Math.max(...used) : 0) + 1).padStart(3, '0')}`
}

function validEntrust(e: EntrustRef): EntrustRef {
  if (e.kind === 'run') { const r = validRunRef(e, 'entrustedBy'); return e.node ? { kind: 'run', ...r, node: e.node } : { kind: 'run', ...r } }
  if (e.kind === 'file') {
    const p = normalizeRepoPath(e.path)
    if (!p || p === '.') throw new RequestError(400, `entrustedBy file "${e.path}" must be a project-relative path`)
    return { kind: 'file', path: p }
  }
  if (e.kind === 'note' && e.text.trim()) return { kind: 'note', text: e.text.trim() }
  throw new RequestError(400, 'entrustedBy must be a run, a project file or a note')
}

// Validates the source workflow and its transitive delegates and returns their
// saved bytes, keyed by workflow id.
async function sourceBundle(ws: Workspace, workflow: string): Promise<{ root: string; files: Record<string, { source: string; text: string; workflow: Workflow }>; warnings: string[] }> {
  const { list } = await ws.workflowSummaries()
  const find = (name: string) => list.find(s => s.id === name) ?? list.find(s => s.file === name || s.file === `${name}.yaml` || s.file === `${name}.yml`)
  const first = find(workflow)
  if (!first?.id) throw new RequestError(404, `no workflow "${workflow}" in ${WORKFLOWS_DIR} (by id or file name)${first?.problem ? `: ${first.problem.message}` : ''}`)
  const files: Record<string, { source: string; text: string; workflow: Workflow }> = {}
  const warnings: string[] = []
  const queue = [first.id]
  while (queue.length) {
    const id = queue.shift()!
    if (files[id]) continue
    const s = list.find(x => x.id === id)
    if (!s) throw new RequestError(409, `workflow "${id}" (a delegate target) does not exist in ${WORKFLOWS_DIR}`)
    const r = await ws.workflowResponse(s.file)
    if (!r.workflow || r.text === null) throw new RequestError(409, `${s.file} cannot be read: ${r.problem?.message}`)
    const errors = r.issues.filter(i => i.severity === 'error')
    if (errors.length) throw new RequestError(409, `${s.file} has validation errors; a run needs a valid definition (wfe validate ${id})`, errors)
    for (const i of r.issues) warnings.push(`${id}: ${i.code}: ${i.message}`)
    files[id] = { source: `${WORKFLOWS_DIR}/${s.file}`, text: r.text, workflow: r.workflow }
    for (const n of Object.values(r.workflow.nodes)) if (n.type === 'delegate' && n.workflow) queue.push(n.workflow)
  }
  return { root: first.id, files, warnings }
}

async function definitionRef(root: string, files: Record<string, { source: string; text: string; workflow: Workflow }>, warnings: string[]): Promise<DefinitionRef> {
  const workflows: Record<string, BundleEntry> = {}
  for (const [id, f] of Object.entries(files).sort(([a], [b]) => (a < b ? -1 : 1))) {
    const states = await approvalStates(f.workflow)
    workflows[id] = {
      file: `${DEFINITION_DIR}/${id}.yaml`, source: f.source, sha256: sha256(f.text),
      definitionDigest: await semanticDigest('definition', f.workflow),
      approvals: { intent: states.intent.status, definition: states.definition.status },
    }
  }
  return { root, workflows, warnings }
}

async function repoContext(ws: Workspace, files: Record<string, { workflow: Workflow }>): Promise<{ repositories: RepoContext[] }> {
  const bound = new Set(['.'])
  for (const f of Object.values(files)) for (const b of Object.values(f.workflow.repositories)) { const p = normalizeRepoPath(b.path); if (p) bound.add(p) }
  const repos = await ws.repositories()
  return {
    repositories: repos.filter(r => bound.has(r.path)).map(r => ({ path: r.path, head: r.head ?? null, branch: r.branch ?? null, dirty: r.initialized ? r.dirty : null })),
  }
}

// Writes a new run folder. The folder is created exclusively: an existing run
// is refused and left as it is. run.json is written last.
async function writeRun(ws: Workspace, ref: RunRef, files: Record<string, string>, record: RunRecord): Promise<CreatedRun> {
  const rel = runDir(ref)
  const runs = await inside(ws.root, `devdocs/${ref.workflow}/runs`)
  await mkdir(runs, { recursive: true })
  const dir = await inside(ws.root, rel)
  try {
    await mkdir(dir)
  } catch (e) {
    if ((e as NodeJS.ErrnoException).code === 'EEXIST') throw new RequestError(409, `run ${runKey(ref)} already exists (${rel}); nothing was changed. Choose another --name or omit it for the next number.`)
    throw e
  }
  await mkdir(join(dir, DEFINITION_DIR))
  const written: string[] = []
  for (const [name, text] of Object.entries(files)) {
    await writeFile(join(dir, name), text, { flag: 'wx' })
    written.push(`${rel}/${name}`)
  }
  await atomicWrite(join(dir, RUN_FILE), `${JSON.stringify(record, null, 2)}\n`)
  written.push(`${rel}/${RUN_FILE}`)
  return { ref, dir: rel, record, files: written }
}

function inputOf(o: CreateRunOptions['input']): { input: RunInput; files: Record<string, string> } {
  if (!o.text.trim()) throw new RequestError(400, `the ${o.kind} text is empty`)
  if (o.kind === 'braindump') {
    if (!o.author?.trim()) throw new RequestError(400, 'a braindump needs its author: the person whose words it holds (--author)')
    const input: RunInput = { kind: 'braindump', file: 'braindump.md', author: o.author.trim() }
    if (o.recordedBy?.trim() && o.recordedBy.trim() !== input.author) input.recordedBy = o.recordedBy.trim()
    return { input, files: { 'braindump.md': o.text } }
  }
  if (!o.requester?.trim()) throw new RequestError(400, 'a request needs its requester: the agent that wrote it (--requester)')
  const input: RunInput = { kind: 'request', file: 'request.md', requester: o.requester.trim(), entrustedBy: validEntrust(o.entrustedBy) }
  if (o.onBehalfOf?.trim()) input.onBehalfOf = o.onBehalfOf.trim()
  const files: Record<string, string> = { 'request.md': o.text }
  if (o.original !== undefined) { input.original = 'original-input.md'; files['original-input.md'] = o.original }
  return { input, files }
}

export async function createRun(ws: Workspace, o: CreateRunOptions): Promise<CreatedRun> {
  if (!o.executor.name?.trim()) throw new RequestError(400, 'the executor is required (--executor <name>): who performs the run')
  const { input, files } = inputOf(o.input)
  // A named run that exists is refused first, whatever the definition's state.
  if (o.name && ID_PATTERN.test(o.workflow) && await stat(await inside(ws.root, runDir({ workflow: o.workflow, run: o.name }))).then(() => true, () => false)) {
    throw new RequestError(409, `run ${o.workflow}/${o.name} already exists (${runDir({ workflow: o.workflow, run: o.name })}); nothing was changed. Choose another --name or omit it for the next number.`)
  }
  const src = await sourceBundle(ws, o.workflow)
  const ref = validRef({ workflow: src.root, run: o.name ?? await nextRunId(ws, src.root) })
  if (o.predecessor) validRunRef(o.predecessor, 'predecessor')
  const definition = await definitionRef(src.root, src.files, src.warnings)
  const context = await repoContext(ws, src.files)
  const graph = graphOf(src.files[src.root].workflow)
  const record = createRecord(ref, input, o, definition, context, graph, null)
  for (const [id, f] of Object.entries(src.files)) files[`${DEFINITION_DIR}/${id}.yaml`] = f.text
  if (o.plan !== undefined) files['plan.md'] = o.plan
  return writeRun(ws, ref, files, record)
}

function createRecord(ref: RunRef, input: RunInput, o: Pick<CreateRunOptions, 'executor' | 'predecessor' | 'by' | 'via' | 'now'>, definition: DefinitionRef, context: { repositories: RepoContext[] }, graph: RunGraph, parent: (RunRef & { node: string }) | null): RunRecord {
  const executor: Executor = { name: o.executor.name.trim(), backend: o.executor.backend?.trim() || null }
  try {
    return operate(null, {
      op: 'run.create', workflow: ref.workflow, run: ref.run, input, executor, predecessor: o.predecessor ?? null, parent,
      definition, context, nodes: Object.keys(graph.nodes).sort(),
    }, { at: (o.now ?? new Date()).toISOString(), by: o.by, via: o.via, graph })
  } catch (e) {
    if (e instanceof RunError) throw new RequestError(400, e.message)
    throw e
  }
}

// ---- operations ------------------------------------------------------------------

export interface OpContext { by?: string; via: string; expectSeq?: number; now?: Date }

async function writeRecord(dir: string, record: RunRecord) {
  await atomicWrite(join(dir, RUN_FILE), `${JSON.stringify(record, null, 2)}\n`)
}

function nextQuestionId(record: RunRecord): string {
  let n = Object.keys(record.questions).length + 1
  while (`q${n}` in record.questions) n++
  return `q${n}`
}

// Applies one operation to a run and writes it. Delegate completion reads the
// child run and records its state as evidence.
export async function runOp(ws: Workspace, ref: RunRef, input: OpInput, ctx: OpContext): Promise<{ record: RunRecord; ref: RunRef }> {
  if (input.op === 'run.create') throw new RequestError(400, 'runs are created with create, not as an operation')
  const { record, graph, dir } = await usableRun(ws, ref)
  const op = structuredClone(input) as OpInput
  if (op.op === 'question.ask' && !op.question) op.question = nextQuestionId(record)
  if (op.op === 'node.complete' && graph.nodes[op.node]?.type === 'delegate') {
    const last = record.nodes[op.node]?.children.at(-1)
    if (last) {
      const child = await readRun(ws, last)
      if (!child.record) throw new RequestError(409, `child run ${runKey(last)} is ${child.problem?.code === 'missing' ? 'missing' : `unreadable (${child.problem?.message})`}; "${op.node}" cannot complete`)
      op.child = { ...last, execution: child.record.execution.state, seq: child.record.seq }
    }
  }
  if (op.op === 'artifact.attach' || (op.op === 'node.complete' && op.artifacts)) {
    for (const p of op.op === 'artifact.attach' ? [op.path] : op.artifacts ?? []) {
      const n = normalizeRepoPath(p)
      if (n && n !== '.') await inside(ws.root, n) // bounds, before anything is written
    }
  }
  let next: RunRecord
  try {
    next = operate(record, op, { at: (ctx.now ?? new Date()).toISOString(), by: ctx.by?.trim() || record.executor.name, via: ctx.via, graph, expectSeq: ctx.expectSeq })
  } catch (e) {
    if (e instanceof RunError) throw new RequestError(e.code === 'outdated' ? 409 : 422, e.message, { code: e.code })
    throw e
  }
  await writeRecord(dir, next)
  return { record: next, ref }
}

// Creates a child run for a running delegate node from the parent's bundle,
// then records the delegation in the parent. The child is written first.
export async function delegate(ws: Workspace, ref: RunRef, node: string, o: { name?: string; request?: string; by?: string; via: string; expectSeq?: number; now?: Date }): Promise<{ parent: RunRecord; child: CreatedRun }> {
  const { record, graph, bundle } = await usableRun(ws, ref)
  const def = graph.nodes[node]
  if (!def) throw new RequestError(422, `node "${node}" is not in this run's definition`)
  if (def.type !== 'delegate' || !def.workflow) throw new RequestError(422, `node "${node}" is a ${def.type} node; only delegate nodes delegate`)
  const by = o.by?.trim() || record.executor.name
  const childId = validRef({ workflow: def.workflow, run: o.name ?? await nextRunId(ws, def.workflow) })
  const at = (o.now ?? new Date()).toISOString()
  // Check the parent operation first, so a refused delegation creates nothing.
  try {
    operate(record, { op: 'node.delegate', node, child: childId }, { at, by, via: o.via, graph, expectSeq: o.expectSeq })
  } catch (e) {
    if (e instanceof RunError) throw new RequestError(e.code === 'outdated' ? 409 : 422, e.message, { code: e.code })
    throw e
  }
  // The child's bundle: its root and transitive delegates, from the parent's bundle.
  const files: Record<string, { source: string; text: string; workflow: Workflow }> = {}
  const queue = [def.workflow]
  while (queue.length) {
    const id = queue.shift()!
    if (files[id]) continue
    const e = bundle.entries[id]
    if (!e?.workflow || e.text === undefined) throw new RequestError(409, `the parent's bundle has no usable "${id}"`)
    files[id] = { source: `${runDir(ref)}/${e.file}`, text: e.text, workflow: e.workflow }
    for (const n of Object.values(e.workflow.nodes)) if (n.type === 'delegate' && n.workflow) queue.push(n.workflow)
  }
  const definition: DefinitionRef = { ...(await definitionRef(def.workflow, files, [])), warnings: record.definition.warnings.filter(w => Object.keys(files).some(id => w.startsWith(`${id}: `))) }
  const text = o.request ?? [
    `# Request: ${def.workflow}`, '',
    `Delegated by ${by} from run ${runKey(ref)}, node "${node}".`, '',
    'The delegate node describes the work as:', '',
    ...(bundle.entries[ref.workflow]?.workflow?.nodes[node]?.description.trim() || '(no description)').split('\n').map(l => `> ${l}`), '',
    '(Written by `wfe run delegate` from the node description; no person authored this text.)', '',
  ].join('\n')
  const input: RunInput = { kind: 'request', file: 'request.md', requester: by, entrustedBy: { kind: 'run', ...ref, node } }
  const parentRef = { ...ref, node }
  const childRecord = createRecord(childId, input, { executor: record.executor, by, via: o.via, now: o.now }, definition, await repoContext(ws, files), graphOf(files[def.workflow].workflow), parentRef)
  const fileTexts: Record<string, string> = { 'request.md': text }
  for (const [id, f] of Object.entries(files)) fileTexts[`${DEFINITION_DIR}/${id}.yaml`] = f.text
  const child = await writeRun(ws, childId, fileTexts, childRecord)
  const r = await runOp(ws, ref, { op: 'node.delegate', node, child: childId }, { by, via: o.via, expectSeq: o.expectSeq, now: o.now })
  return { parent: r.record, child }
}

// ---- checking --------------------------------------------------------------------

export interface RunCheck { ref: string; ok: boolean; problem?: string; code?: string; warnings: string[] }

// The record, its bundle and its relations. Reads only.
export async function checkRun(ws: Workspace, ref: RunRef): Promise<RunCheck> {
  const r = await runResponse(ws, ref)
  const warnings: string[] = []
  if (r.record) {
    if (r.parent && !r.parent.linksBack) warnings.push(`the parent ${r.parent.ref} does not list this run as a child of node ${r.parent.node}${r.parent.problem ? ` (${r.parent.problem})` : ''}`)
    for (const c of r.children) if (c.problem) warnings.push(`child ${c.ref} (node ${c.node}): ${c.problem}`)
    for (const a of r.artifacts) if (!a.exists) warnings.push(`artifact ${a.path} does not exist`)
    const input = r.files.some(f => f.name === r.record!.input.file)
    if (!input) warnings.push(`the input file ${r.record.input.file} is missing`)
  }
  return { ref: r.ref, ok: !!r.record, problem: r.problem?.message, code: r.problem?.code, warnings }
}
