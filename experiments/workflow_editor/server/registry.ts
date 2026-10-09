// Locally registered workspaces. The registry is an ignored, machine-specific
// JSON file; registration says where a workspace is expected, observation
// says what is actually there right now. Nothing here talks to other hosts.
import { readFile, stat } from 'node:fs/promises'
import { join } from 'node:path'
import { git } from './git.ts'
import { parseProject } from './yamlDoc.ts'

export interface Registration { id: string; label: string; host: string; path: string }
export interface Registry { approver: string; workspaces: Registration[] }

export interface Observation {
  available: boolean
  reason?: string // why it is not available
  gitRoot: boolean
  projectId?: string
  projectName?: string
  branch?: string | null
  head?: string
}

export async function loadRegistry(file: string): Promise<Registry> {
  const raw = JSON.parse(await readFile(file, 'utf8')) as Partial<Registry>
  const workspaces = (raw.workspaces ?? []).filter((w): w is Registration =>
    !!w && typeof w.id === 'string' && typeof w.path === 'string')
    .map(w => ({ id: w.id, label: w.label || w.id, host: w.host || 'this machine', path: w.path }))
  const ids = new Set<string>()
  for (const w of workspaces) {
    if (ids.has(w.id)) throw new Error(`registry: duplicate workspace id "${w.id}"`)
    ids.add(w.id)
  }
  return { approver: typeof raw.approver === 'string' ? raw.approver : '', workspaces }
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
