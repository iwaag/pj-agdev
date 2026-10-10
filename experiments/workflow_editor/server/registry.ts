// Locally registered workspaces. The registry is an ignored, machine-specific
// JSON file; registration says where a workspace is expected, observation
// says what is actually there right now. Nothing here talks to other hosts.
import { mkdir, readFile, realpath, stat } from 'node:fs/promises'
import { basename, dirname, join, resolve } from 'node:path'
import type { Diagnostic } from '../shared/api.ts'
import { ID_PATTERN } from '../shared/model.ts'
import { atomicWrite, readTextOrNull } from './files.ts'
import { git } from './git.ts'
import { parseProject } from './yamlDoc.ts'
import { Workspace } from './workspace.ts'

export interface Registration { id: string; label: string; host: string; path: string }
export interface Registry { approver: string; workspaces: Registration[]; exists: boolean }

export interface Observation {
  available: boolean
  reason?: string // why it is not available
  gitRoot: boolean
  projectId?: string
  projectName?: string
  branch?: string | null
  head?: string
}

// A registry that exists but cannot be used. It is reported, never treated as
// empty, and never overwritten.
export class RegistryError extends Error {}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

async function readRaw(file: string): Promise<Record<string, unknown> | null> {
  let text: string | null
  try { text = await readTextOrNull(file) } catch (e) { throw new RegistryError(`registry ${file} cannot be read: ${(e as Error).message}`) }
  if (text === null) return null
  let raw: unknown
  try { raw = JSON.parse(text) } catch (e) { throw new RegistryError(`registry ${file} is not valid JSON (${(e as Error).message}). Fix or remove the file; nothing was changed.`) }
  if (!isObj(raw) || (raw.workspaces !== undefined && !Array.isArray(raw.workspaces))) {
    throw new RegistryError(`registry ${file} must be an object {"approver": "...", "workspaces": [...]}. Fix the file; nothing was changed.`)
  }
  return raw
}

// A missing file is an empty registry (exists: false).
export async function loadRegistry(file: string): Promise<Registry> {
  const raw = await readRaw(file)
  if (!raw) return { approver: '', workspaces: [], exists: false }
  const workspaces = ((raw.workspaces ?? []) as unknown[]).map((w, i) => {
    if (!isObj(w) || typeof w.id !== 'string' || typeof w.path !== 'string') throw new RegistryError(`registry ${file}: workspaces[${i}] needs text "id" and "path". Fix the file; nothing was changed.`)
    return { id: w.id, label: typeof w.label === 'string' && w.label ? w.label : w.id, host: typeof w.host === 'string' && w.host ? w.host : 'this machine', path: w.path }
  })
  const ids = new Set<string>()
  for (const w of workspaces) {
    if (ids.has(w.id)) throw new RegistryError(`registry ${file}: duplicate workspace id "${w.id}"`)
    ids.add(w.id)
  }
  return { approver: typeof raw.approver === 'string' ? raw.approver : '', workspaces, exists: true }
}

export async function observe(reg: Registration): Promise<Observation> {
  try {
    if (!(await stat(reg.path)).isDirectory()) return { available: false, gitRoot: false, reason: 'not a directory' }
  } catch {
    return { available: false, gitRoot: false, reason: 'directory not found on this machine' }
  }
  const top = await git(reg.path, ['rev-parse', '--show-toplevel'])
  if (top.code !== 0) return { available: false, gitRoot: false, reason: 'not a Git repository' }
  const head = await git(reg.path, ['rev-parse', 'HEAD'])
  const branch = await git(reg.path, ['symbolic-ref', '-q', '--short', 'HEAD'])
  const obs: Observation = {
    available: true, gitRoot: true,
    head: head.code === 0 ? head.stdout.trim() : undefined,
    branch: branch.code === 0 ? branch.stdout.trim() : null,
  }
  try {
    const parsed = parseProject(await readFile(join(reg.path, 'project.yaml'), 'utf8'))
    if (parsed.ok) { obs.projectId = parsed.model.id; obs.projectName = parsed.model.name }
    else obs.reason = `project.yaml: ${parsed.problem.message}`
  } catch {
    obs.reason = 'no project.yaml'
  }
  return obs
}

export interface RegisterResult {
  ok: boolean
  status: 'registered' | 'already-registered' | 'refused'
  message: string
  registration?: Registration
  diagnostics: Diagnostic[]
}

async function same(a: string, b: string) {
  const [ra, rb] = await Promise.all([realpath(a).catch(() => resolve(a)), realpath(b).catch(() => resolve(b))])
  return ra === rb
}

// Records the Git root that contains `dir`. Repeating it for the same root
// changes nothing; other entries and fields of the registry are kept.
export async function registerWorkspace(file: string, dir: string, opts: { id?: string; label?: string } = {}): Promise<RegisterResult> {
  const abs = resolve(dir)
  if (!(await stat(abs).then(s => s.isDirectory(), () => false))) {
    return { ok: false, status: 'refused', message: `${abs} is not a directory`, diagnostics: [] }
  }
  const top = await git(abs, ['rev-parse', '--show-toplevel'])
  if (top.code !== 0) return { ok: false, status: 'refused', message: `${abs} is not inside a Git repository; a workspace is a project's Git root`, diagnostics: [] }
  const root = await realpath(top.stdout.trim())
  const structure = await new Workspace({ id: '', label: '', host: '', path: root }).structure()
  const raw = await readRaw(file) ?? { approver: '', workspaces: [] }
  const current = await loadRegistry(file)
  for (const w of current.workspaces) {
    if (await same(w.path, root)) {
      return { ok: true, status: 'already-registered', message: `${root} is already registered as workspace "${w.id}"`, registration: w, diagnostics: structure.diagnostics }
    }
  }
  const id = opts.id ?? structure.projectId ?? basename(root).toLowerCase().replace(/[^a-z0-9_.-]+/g, '-').replace(/^[^a-z0-9]+/, '')
  if (!ID_PATTERN.test(id)) return { ok: false, status: 'refused', message: `"${id}" cannot be a workspace id (${ID_PATTERN.source}); choose one with --id`, diagnostics: structure.diagnostics }
  const taken = current.workspaces.find(w => w.id === id)
  if (taken) return { ok: false, status: 'refused', message: `workspace id "${id}" is already registered for ${taken.path}; choose another with --id`, diagnostics: structure.diagnostics }
  const registration: Registration = { id, label: opts.label || structure.projectName || id, host: 'this machine', path: root }
  raw.workspaces = [...((raw.workspaces as unknown[] | undefined) ?? []), registration]
  if (typeof raw.approver !== 'string') raw.approver = ''
  await mkdir(dirname(file), { recursive: true })
  await atomicWrite(file, `${JSON.stringify(raw, null, 2)}\n`)
  return { ok: true, status: 'registered', message: `Registered ${root} as workspace "${id}"`, registration, diagnostics: structure.diagnostics }
}

// The registered workspace whose root contains `dir`, if any.
export async function workspaceAt(reg: Registry, dir: string): Promise<Registration | undefined> {
  const real = await realpath(dir).catch(() => resolve(dir))
  let best: Registration | undefined, bestLen = -1
  for (const w of reg.workspaces) {
    const root = await realpath(w.path).catch(() => resolve(w.path))
    if ((real === root || real.startsWith(root + '/')) && root.length > bestLen) { best = w; bestLen = root.length }
  }
  return best
}
