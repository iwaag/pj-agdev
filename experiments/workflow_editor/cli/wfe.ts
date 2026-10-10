#!/usr/bin/env node
// wfe — the workflow editor's command-line surface. A thin client of the same
// modules the service uses (server/*, shared/*); it never goes through the
// service, so no command needs it running. `wfe help` is the index.
import { spawn } from 'node:child_process'
import { realpathSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Diagnostic, RepositoryStatus, WorkflowSummary } from '../shared/api.ts'
import { autoArrange } from '../shared/layout.ts'
import { APPROVAL_KINDS, type ApprovalKind, type Issue } from '../shared/model.ts'
import { createProject } from '../server/create.ts'
import { loadRegistry, observe, registerWorkspace, RegistryError, workspaceAt, type Registration } from '../server/registry.ts'
import { RequestError, Workspace } from '../server/workspace.ts'
import { setupArea } from './setup.ts'

const here = dirname(fileURLToPath(import.meta.url))
export const EXPERIMENT = resolve(here, '..')
export const CONTRACT = join(EXPERIMENT, 'docs', 'contract.md')
const DEFAULT_REGISTRY = resolve(EXPERIMENT, '..', '..', '.local', 'workflow-editor', 'registry.json')

class UsageError extends Error {}
class Refused extends Error { detail?: unknown; constructor(m: string, detail?: unknown) { super(m); this.detail = detail } }

// ---- arguments ---------------------------------------------------------------

interface Parsed { positional: string[]; opts: Map<string, string[]>; flags: Set<string> }
const FLAGS = new Set(['json', 'help', 'resume', 'h'])
function parse(argv: string[]): Parsed {
  const p: Parsed = { positional: [], opts: new Map(), flags: new Set() }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--') { p.positional.push(...argv.slice(i + 1)); break }
    if (a.startsWith('--') || a === '-h' || a === '-w') {
      const [k, inline] = a === '-h' ? ['help'] : a === '-w' ? ['workspace'] : a.slice(2).split(/=(.*)/s, 2)
      if (FLAGS.has(k)) { p.flags.add(k); continue }
      const v = inline ?? argv[++i]
      if (v === undefined) throw new UsageError(`--${k} needs a value`)
      p.opts.set(k, [...(p.opts.get(k) ?? []), v])
    } else p.positional.push(a)
  }
  return p
}
const opt = (p: Parsed, k: string) => p.opts.get(k)?.at(-1)

// ---- context -----------------------------------------------------------------

const registryFile = (p: Parsed) => resolve(opt(p, 'registry') ?? process.env.WFE_REGISTRY ?? DEFAULT_REGISTRY)
const areaDir = (p: Parsed) => resolve(opt(p, 'area') ?? process.env.WFE_AREA ?? dirname(registryFile(p)))
const port = (p: Parsed) => Number(opt(p, 'port') ?? process.env.WFE_PORT ?? 8095)

async function workspace(p: Parsed): Promise<Workspace> {
  const reg = await loadRegistry(registryFile(p))
  const id = opt(p, 'workspace')
  let w: Registration | undefined
  if (id) {
    w = reg.workspaces.find(x => x.id === id)
    if (!w) throw new Refused(`workspace "${id}" is not registered in ${registryFile(p)} (see: wfe list)`)
  } else {
    w = await workspaceAt(reg, process.cwd())
    if (!w) throw new Refused(`the current directory is not inside a registered workspace; pass --workspace <id> (see: wfe list), or register it (wfe register)`)
  }
  const o = await observe(w)
  if (!o.available) throw new Refused(`workspace "${w.id}" is registered but not available: ${o.reason}`)
  return new Workspace(w)
}

async function workflowFile(ws: Workspace, name: string): Promise<string> {
  const { list } = await ws.workflowSummaries()
  const hit = list.find(s => s.file === name) ?? list.find(s => s.file === `${name}.yaml` || s.file === `${name}.yml`) ?? list.find(s => s.id === name)
  if (!hit) throw new Refused(`no workflow "${name}" in ${ws.root}/devdocs/workflows (by file name or id); see: wfe status`)
  return hit.file
}

async function serviceState(p: Parsed): Promise<{ url: string; running: boolean; sameRegistry?: boolean; registry?: string }> {
  const url = `http://127.0.0.1:${port(p)}`
  try {
    const r = await fetch(`${url}/api/workspaces`, { signal: AbortSignal.timeout(800) })
    const body = await r.json() as { registry?: { path?: string } }
    return { url, running: true, sameRegistry: body.registry?.path === registryFile(p), registry: body.registry?.path }
  } catch { return { url, running: false } }
}

// ---- output ------------------------------------------------------------------

let json = false
const out = (human: string, data: unknown) => { console.log(json ? JSON.stringify(data, null, 2) : human) }
const short = (h?: string | null) => (h ? h.slice(0, 7) : '—')
const diag = (d: Diagnostic) => `  ${d.severity === 'error' ? 'error  ' : 'warning'} ${d.message}${d.fix ? `\n           fix: ${d.fix}` : ''}`
const issueLine = (i: Issue) => `  ${i.severity === 'error' ? 'error  ' : 'warning'} ${i.code.padEnd(26)} ${i.message}`
function repoLine(r: RepositoryStatus) {
  const parts = [r.path.padEnd(22), r.category.padEnd(8)]
  if (!r.initialized) parts.push('not initialized')
  else parts.push(`${r.branch ?? 'detached'} @ ${short(r.head)}`)
  if (r.kind === 'submodule' && r.recorded) parts.push(`recorded ${short(r.recorded)}${r.staged ? `, staged ${short(r.staged)}` : ''}${r.matchesRecorded === false ? ' (HEAD differs)' : ''}`)
  if (r.dirty) parts.push(`${r.dirty} uncommitted`)
  if (r.error) parts.push(`error: ${r.error}`)
  return `  ${parts.join('  ')}`
}
function workflowLine(w: WorkflowSummary) {
  if (w.problem) return `  ${w.file.padEnd(24)} cannot be read: ${w.problem.kind}: ${w.problem.message}`
  const ap = w.approvals ? `intent ${w.approvals.intent}, definition ${w.approvals.definition}` : ''
  return `  ${w.file.padEnd(24)} id ${w.id}  "${w.name}"  ${w.errors} error${w.errors === 1 ? '' : 's'}, ${w.warnings} warning${w.warnings === 1 ? '' : 's'}  ${ap}`
}

// ---- help --------------------------------------------------------------------

const HELP: Record<string, string> = {
  create: `wfe create <dir> --name <name> [--id <id>] [--intent <text>] [--goal <text>]... [--devdocs-source <path|url>] [--resume]

Creates a new project and registers it as a workspace.
  Writes  <dir>/ as a new Git repository with project.yaml (ag.project.v1),
          .gitignore (.local/), an empty .local/, and devdocs/ as a submodule.
  Source  devdocs comes from a new local repository <area>/sources/<id>-devdocs.git
          (or --sources <dir>), or from --devdocs-source. A local source is
          recorded as a URL relative to <dir>, so the area can move as a whole.
  Commits two commits with your Git identity (user.name/user.email): the new
          devdocs source's initial commit (README.md, workflows/) and the
          project root's initial commit. Nothing is pushed. If the identity is
          missing, nothing is created.
  Refuses a <dir> that exists and is not empty; it never overwrites.
  --id    stable project id (default: <dir>'s name without "pj-")
  --resume continues a creation that stopped partway (it left
          <dir>/.local/wfe-create.json); finished steps are kept, nothing is deleted.
Result: the steps done or kept, the commits, the workspace id, and any
structure diagnostics. Exit 0 created; 1 refused or stopped (the message says
what exists and how to continue).`,
  register: `wfe register [<dir>] [--id <id>] [--label <text>]

Records the Git root containing <dir> (default: the current directory) in the
registry, so the editor and the other commands can use it.
  Changes only the registry file; other entries are kept. Registering the same
          root again changes nothing and reports the existing id.
  --id    workspace id (default: the project id from project.yaml)
Result: registered / already-registered / refused, plus diagnostics for what
the project structure lacks (project.yaml, devdocs submodule, .gitignore …),
each with its fix. Exit 0 registered or already registered; 1 refused.`,
  list: `wfe list

Lists the registered workspaces and what is observed now: available or not
(and why), project id and name, branch and HEAD. Reads only.`,
  status: `wfe status [--workspace <id>]

Shows one workspace: project id, name, intent and goals; structure diagnostics;
every repository with Git state (branch or detached HEAD, recorded/staged
gitlink, uncommitted entries, not initialized); every workflow with its id,
validation counts and approval states; and whether the editor service is
running. Reads only. The workspace is the one containing the current
directory unless --workspace is given.`,
  validate: `wfe validate [<workflow>] [--workspace <id>]

Validates one workflow (file name or id) or all of them with the same rules as
the editor (docs/contract.md, "Validation"). Reads only.
Result: each issue as severity, code and message. Exit 0 when there are no
errors (warnings allowed); 1 when a workflow has errors or cannot be read.
Validation checks structure and references; it is not an approval.`,
  approve: `wfe approve <workflow> <intent|definition> --approver <name>

Records an approval of the saved file, exactly as the editor's Approve buttons
do: the digest of the current intent (or definition), the declared approver
and the time are written into the workflow's approvals.
  Refuses a definition with validation errors, an empty intent, or a file that
          cannot be read.
  --approver is required: the name of the person who approves. The approver
          is declared, not authenticated; passing validation is not an approval.
Exit 0 recorded; 1 refused.`,
  arrange: `wfe arrange <workflow>

Auto-arrange: replaces layout.nodes with positions computed by rank, the same
algorithm as the editor's Auto-arrange button, and saves the file. Only
layout changes; approvals are unaffected. Refuses a file that cannot be read.`,
  'add-repo': `wfe add-repo <path> <location> [--workspace <id>]

Adds a Git submodule at <path> (for example study/evals) from <location>, the
same operation as the project view's "Add submodule": git submodule add.
A relative location resolves against the project's origin, or against the
project root when it has no remote. Local file transport is enabled for this
command only. The result is staged in the project root, not committed.
Exit 0 added; 1 failed (what Git left behind is reported; nothing is reset).`,
  workflow: `wfe workflow new <id> [--name <name>] [--workspace <id>]

Creates devdocs/workflows/<id>.yaml with the editor's template (schema, id,
name, empty intent, no nodes), as the project view's "New workflow" does.
Refuses an id already used by another workflow file. Writing the file by hand
is equally valid; see docs/contract.md.`,
  serve: `wfe serve [--port <port>]

Starts the editor service for this registry in the foreground: it builds the
UI, then serves the UI and API on http://127.0.0.1:<port>/ (default 8095, or
WFE_PORT). Stop it with Ctrl-C. Browser-created projects go beneath the
authoring area. Open views follow file changes without a reload.`,
  setup: `wfe setup <area> [--port <port>]

Creates or refreshes an authoring area: <area>/AGENTS.md (from the tracked
template), <area>/wfe (a launcher that pins this area's registry and port), an
empty registry if none exists, and sources/. It never creates or changes a
project, and keeps an existing registry and everything else in the area.
Prints the directory, the tool, the service command, the URL and a first
prompt.`,
}

function index(p: Parsed): string {
  return `wfe — create and register Git-backed projects; inspect, validate, approve and arrange their workflows.

Usage: wfe <command> [options]        wfe help <command>   (or <command> --help)

Projects and workspaces
  create <dir> --name …     create a project (Git root, project.yaml, devdocs submodule) and register it
  register [<dir>]          register an existing project's Git root
  list                      registered workspaces and what is observed
  status                    project, repositories (Git state), workflows, editor service
  add-repo <path> <loc>     add a Git submodule (git submodule add)

Workflows (by file name or id)
  workflow new <id>         create devdocs/workflows/<id>.yaml from the template
  validate [<workflow>]     validation issues
  approve <wf> <kind>       record an intent or definition approval by a named approver
  arrange <workflow>        auto-arrange the layout

Editor
  serve                     start the editor (UI and API) for this registry
  setup <area>              create or refresh an authoring area and its AGENTS.md

Options: --workspace <id> (default: the workspace containing the current directory),
         --json (structured output), --registry <file>, --area <dir>
Registry: ${registryFile(p)}
File contract (project.yaml, workflow YAML, validation, approvals): ${CONTRACT}
No command needs the editor service. Definition files may also be edited directly;
an open editor view follows the change. Exit codes: 0 ok, 1 refused or errors, 2 usage.`
}

// ---- commands ----------------------------------------------------------------

async function cmdCreate(p: Parsed): Promise<number> {
  const [dirArg] = p.positional
  if (!dirArg) throw new UsageError('create needs a destination directory')
  const name = opt(p, 'name')
  if (!name) throw new UsageError('create needs --name')
  const dir = resolve(dirArg)
  const id = opt(p, 'id') ?? dir.split('/').pop()!.replace(/^pj-/, '')
  const r = await createProject({
    dir, id, name, intent: opt(p, 'intent') ?? '', goals: p.opts.get('goal') ?? [],
    sourcesDir: resolve(opt(p, 'sources') ?? join(areaDir(p), 'sources')),
    devdocsSource: opt(p, 'devdocs-source'), registryFile: registryFile(p), resume: p.flags.has('resume'),
  })
  const lines = [r.message, ...r.steps.map(s => `  ${s.status.padEnd(6)} ${s.name}: ${s.detail}`)]
  if (r.commits.length) lines.push('Commits:', ...r.commits.map(c => `  ${short(c.commit)} ${c.message} (${c.repository})`))
  if (r.diagnostics?.length) lines.push('Structure:', ...r.diagnostics.map(diag))
  if (r.ok) lines.push(`Next: cd ${r.root}; write workflows in devdocs/workflows/ (wfe workflow new <id>); wfe status`)
  out(lines.join('\n'), r)
  return r.ok ? 0 : 1
}

async function cmdRegister(p: Parsed): Promise<number> {
  const r = await registerWorkspace(registryFile(p), resolve(p.positional[0] ?? '.'), { id: opt(p, 'id'), label: opt(p, 'label') })
  out([r.message, ...(r.diagnostics.length ? ['Structure:', ...r.diagnostics.map(diag)] : [])].join('\n'), r)
  return r.ok ? 0 : 1
}

async function cmdList(p: Parsed): Promise<number> {
  const reg = await loadRegistry(registryFile(p))
  const rows = await Promise.all(reg.workspaces.map(async w => ({ ...w, observed: await observe(w) })))
  const human = !reg.exists ? `No registry yet at ${registryFile(p)}; create or register a project.`
    : rows.length === 0 ? 'No workspaces registered.'
      : rows.map(w => `${w.id.padEnd(16)} ${w.observed.available ? 'available' : 'unavailable'}  ${w.observed.available
        ? `project ${w.observed.projectId ?? '?'} "${w.observed.projectName ?? ''}"  ${w.observed.branch ?? 'detached'} @ ${short(w.observed.head)}${w.observed.reason ? `  (${w.observed.reason})` : ''}`
        : w.observed.reason}\n${' '.repeat(17)}${w.path}`).join('\n')
  out(human, { registry: registryFile(p), exists: reg.exists, workspaces: rows })
  return 0
}

async function cmdStatus(p: Parsed): Promise<number> {
  const ws = await workspace(p)
  const r = await ws.projectResponse()
  const svc = await serviceState(p)
  const pr = r.project
  const lines = [
    `Workspace ${ws.reg.id}: ${ws.root}`,
    pr ? `Project ${pr.id} "${pr.name}"` : `project.yaml: ${r.problem?.message}`,
    ...(pr ? [`Intent: ${pr.intent.trim() || '(empty)'}`, 'Goals:', ...(pr.goals.length ? pr.goals.map(g => `  - ${g}`) : ['  (none)'])] : []),
    r.structure.length ? 'Structure:' : 'Structure: complete', ...r.structure.map(diag),
    'Repositories:', ...r.repositories.map(repoLine),
    `Workflows (devdocs/workflows):${r.workflowsDir.exists ? '' : ` ${r.workflowsDir.reason}`}`,
    ...(r.workflows.length ? r.workflows.map(workflowLine) : ['  (none)']),
    svc.running ? `Editor: running at ${svc.url}/${svc.sameRegistry ? `#/ws/${encodeURIComponent(ws.reg.id)}` : ` — but it serves ${svc.registry ? `another registry (${svc.registry})` : 'another registry or an older version'}; start this one with: wfe serve --port <free port>`}`
      : `Editor: not running at ${svc.url} (start it with: wfe serve)`,
  ]
  out(lines.join("\n"), { ...r, workspace: ws.reg.id, root: ws.root, editor: svc })
  return 0
}

async function cmdValidate(p: Parsed): Promise<number> {
  const ws = await workspace(p)
  const files = p.positional[0] ? [await workflowFile(ws, p.positional[0])] : await ws.workflowFiles()
  const results = []
  for (const f of files) {
    const r = await ws.workflowResponse(f)
    results.push({ file: f, id: r.workflow?.id, problem: r.problem, issues: r.issues })
  }
  const bad = results.filter(r => r.problem || r.issues.some(i => i.severity === 'error')).length
  const human = results.length === 0 ? 'No workflows in devdocs/workflows.' : results.map(r =>
    `${r.file}${r.id ? ` (id ${r.id})` : ''}: ${r.problem ? `cannot be read — ${r.problem.kind}: ${r.problem.message}${r.problem.line ? ` (line ${r.problem.line})` : ''}`
      : r.issues.length ? `${r.issues.filter(i => i.severity === 'error').length} errors, ${r.issues.filter(i => i.severity === 'warning').length} warnings\n${r.issues.map(issueLine).join('\n')}` : 'valid'}`).join('\n')
  out(human, { workspace: ws.reg.id, ok: bad === 0, workflows: results })
  return bad ? 1 : 0
}

async function cmdApprove(p: Parsed): Promise<number> {
  const [name, kind] = p.positional
  if (!name || !kind) throw new UsageError('approve needs <workflow> and <intent|definition>')
  if (!(APPROVAL_KINDS as readonly string[]).includes(kind)) throw new UsageError('the kind is intent or definition')
  const approver = opt(p, 'approver')
  if (!approver?.trim()) throw new UsageError('approve needs --approver <name>: the person who approves')
  const ws = await workspace(p)
  const file = await workflowFile(ws, name)
  try {
    const r = await ws.approve(file, kind as ApprovalKind, approver)
    out(`Recorded ${kind} approval of ${file} by ${approver.trim()}: ${r.state.status} (${r.state.digest})`, { ok: true, file, kind, approver: approver.trim(), state: r.state })
    return 0
  } catch (e) {
    if (e instanceof RequestError) throw new Refused(`approval refused: ${e.message}`, e.detail)
    throw e
  }
}

async function cmdArrange(p: Parsed): Promise<number> {
  const [name] = p.positional
  if (!name) throw new UsageError('arrange needs <workflow>')
  const ws = await workspace(p)
  const file = await workflowFile(ws, name)
  const read = await ws.readWorkflowFile(file)
  if (!read.workflow || read.text === null) throw new Refused(`${file} cannot be arranged: ${read.problem?.message ?? 'unreadable'}`)
  const next = structuredClone(read.workflow)
  autoArrange(next)
  try {
    const saved = await ws.saveWorkflow(file, next)
    const changed = saved.text !== read.text
    out(`${changed ? 'Arranged' : 'Already arranged'}: ${file} (${Object.keys(next.layout.nodes).length} positions)`, { ok: true, file, changed, layout: next.layout })
    return 0
  } catch (e) {
    if (e instanceof RequestError) throw new Refused(e.message, e.detail)
    throw e
  }
}

async function cmdAddRepo(p: Parsed): Promise<number> {
  const [path, location] = p.positional
  if (!path || !location) throw new UsageError('add-repo needs <path> and <location>')
  const ws = await workspace(p)
  try {
    const r = await ws.addSubmodule(path, location)
    const lines = [r.message, ...(r.stderr ? [r.stderr] : [])]
    if (r.partial) lines.push(`Left behind — .gitmodules entry: ${r.partial.gitmodulesEntry}; path exists: ${r.partial.pathExists}; staged: ${r.partial.staged}; module git dir: ${r.partial.gitDirExists}`)
    out(lines.join('\n'), r)
    return r.ok ? 0 : 1
  } catch (e) {
    if (e instanceof RequestError) throw new Refused(e.message)
    throw e
  }
}

async function cmdWorkflow(p: Parsed): Promise<number> {
  const [sub, id] = p.positional
  if (sub !== 'new' || !id) throw new UsageError('usage: wfe workflow new <id> [--name <name>]')
  const ws = await workspace(p)
  try {
    const r = await ws.createWorkflow(id, opt(p, 'name') ?? '')
    const path = join(ws.root, 'devdocs', 'workflows', r.file)
    out(`Created ${path}. Fill in intent, repositories, nodes and edges (docs/contract.md).`, { ok: true, file: r.file, path })
    return 0
  } catch (e) {
    if (e instanceof RequestError) throw new Refused(e.message)
    throw e
  }
}

async function cmdSetup(p: Parsed): Promise<number> {
  const [dir] = p.positional
  if (!dir) throw new UsageError('setup needs the area directory')
  const r = await setupArea(resolve(dir), { port: port(p) })
  out(r.summary, r)
  return r.files.some(f => f.status === 'error') ? 1 : 0
}

async function cmdServe(p: Parsed): Promise<number> {
  const build = spawn(process.execPath, [join(EXPERIMENT, 'node_modules', 'vite', 'bin', 'vite.js'), 'build', '--logLevel', 'warn'], { cwd: EXPERIMENT, stdio: 'inherit' })
  const built = await new Promise<number>(r => build.on('exit', c => r(c ?? 1)))
  if (built !== 0) { console.error('wfe serve: building the UI failed; run npm ci in the experiment first'); return 1 }
  const child = spawn(process.execPath, [join(EXPERIMENT, 'server', 'main.ts'), '--serve-dist', '--port', String(port(p)), '--registry', registryFile(p), '--area', areaDir(p)], { stdio: 'inherit' })
  for (const s of ['SIGINT', 'SIGTERM'] as const) process.on(s, () => child.kill(s))
  return new Promise<number>(r => child.on('exit', c => r(c ?? 0)))
}

const COMMANDS: Record<string, (p: Parsed) => Promise<number>> = {
  create: cmdCreate, register: cmdRegister, list: cmdList, status: cmdStatus, validate: cmdValidate,
  approve: cmdApprove, arrange: cmdArrange, 'add-repo': cmdAddRepo, workflow: cmdWorkflow, serve: cmdServe, setup: cmdSetup,
}

export async function main(argv: string[]): Promise<number> {
  let p: Parsed
  try { p = parse(argv) } catch (e) { console.error(`wfe: ${(e as Error).message}`); return 2 }
  json = p.flags.has('json')
  const [cmd, ...rest] = p.positional
  if (!cmd || cmd === 'help' || (!cmd && p.flags.has('help'))) {
    const topic = cmd === 'help' ? rest[0] : undefined
    if (topic && HELP[topic]) console.log(HELP[topic])
    else if (topic) { console.error(`wfe: no command "${topic}"\n`); console.log(index(p)); return 2 }
    else console.log(index(p))
    return 0
  }
  if (!COMMANDS[cmd]) { console.error(`wfe: no command "${cmd}" (see: wfe help)`); return 2 }
  if (p.flags.has('help')) { console.log(HELP[cmd]); return 0 }
  p.positional = rest
  try {
    return await COMMANDS[cmd](p)
  } catch (e) {
    if (e instanceof UsageError) { console.error(`wfe ${cmd}: ${e.message}\n\n${HELP[cmd]}`); return 2 }
    if (e instanceof Refused || e instanceof RegistryError) {
      const detail = (e as Refused).detail
      if (json) console.log(JSON.stringify({ ok: false, error: e.message, detail }, null, 2))
      else {
        console.error(`wfe ${cmd}: ${e.message}`)
        if (Array.isArray(detail)) for (const i of detail as Issue[]) console.error(issueLine(i))
      }
      return 1
    }
    throw e
  }
}

const invoked = (() => { try { return realpathSync(process.argv[1] ?? '') === fileURLToPath(import.meta.url) } catch { return false } })()
if (invoked) process.exitCode = await main(process.argv.slice(2))
