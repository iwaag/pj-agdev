// Creates a new local project and registers it: a root Git repository with
// project.yaml, .gitignore (.local/) and devdocs as a submodule. Shared by the
// service (browser "Create project") and the CLI (`wfe create`).
//
// Two commits are made, both with the person's own Git identity: the initial
// commit of a new devdocs source (README.md, workflows/) and the project
// root's initial commit. Nothing is pushed. Later saves only write files.
//
// A creation that stops partway leaves a marker (.local/wfe-create.json) in
// the destination and reports which steps finished. Running it again with
// `resume` continues from there; nothing that exists is deleted or replaced.
import { mkdir, readdir, rm, stat, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { isAbsolute, join, relative, resolve, sep } from 'node:path'
import type { CreateProjectResult, CreateStep } from '../shared/api.ts'
import { ID_PATTERN, PROJECT_SCHEMA } from '../shared/model.ts'
import { readTextOrNull } from './files.ts'
import { git, gitOk, LOCAL_TRANSPORT } from './git.ts'
import { registerWorkspace } from './registry.ts'
import { Workspace } from './workspace.ts'
import { newProjectText, parseProject } from './yamlDoc.ts'

export interface CreateProjectOptions {
  dir: string // destination, absolute
  id: string
  name: string
  intent: string
  goals: string[]
  sourcesDir: string // where a new devdocs source repository is created
  devdocsSource?: string // an existing devdocs repository (path or URL) instead
  registryFile: string
  workspaceId?: string
  resume?: boolean
  env?: Record<string, string> // extra Git environment (tests)
  failAfter?: string // test hook: stop after this step
}

const MARKER = '.local/wfe-create.json'
const exists = (p: string) => stat(p).then(() => true, () => false)
const isUrl = (s: string) => /^[a-z][a-z0-9+.-]*:\/\//i.test(s) || /^[^/\\]+@[^:]+:/.test(s)
const posix = (p: string) => p.split(sep).join('/')

// The person's identity as Git would use it. Missing values are reported;
// no fallback identity is invented.
export async function gitIdentity(env: Record<string, string> = {}): Promise<{ name?: string; email?: string }> {
  const get = async (key: string, envKey: string) => {
    const fromEnv = env[envKey] ?? process.env[envKey]
    if (fromEnv) return fromEnv
    const r = await git(tmpdir(), ['config', '--get', key], { env })
    return r.code === 0 && r.stdout.trim() ? r.stdout.trim() : undefined
  }
  return { name: await get('user.name', 'GIT_AUTHOR_NAME'), email: await get('user.email', 'GIT_AUTHOR_EMAIL') }
}

export async function createProject(o: CreateProjectOptions): Promise<CreateProjectResult> {
  const dir = resolve(o.dir)
  const steps: CreateStep[] = []
  const commits: CreateProjectResult['commits'] = []
  const result = (ok: boolean, message: string, extra: Partial<CreateProjectResult> = {}): CreateProjectResult =>
    ({ ok, message, root: dir, steps, commits, ...extra })
  const step = (name: string, status: CreateStep['status'], detail: string) => { steps.push({ name, status, detail }) }
  const env = o.env ?? {}
  const run = (cwd: string, args: string[]) => gitOk(cwd, args, { env, config: { ...LOCAL_TRANSPORT, 'init.defaultBranch': 'main' }, timeoutMs: 120_000 })
  const stop = (name: string) => { if (o.failAfter === name) throw new Error(`stopped after "${name}" (test hook)`) }

  // ---- checks that write nothing ----
  if (!ID_PATTERN.test(o.id)) return result(false, `project id "${o.id}" must match ${ID_PATTERN.source}`)
  if (!o.name.trim()) return result(false, 'a project name is required')
  if (!isAbsolute(o.dir)) return result(false, 'the destination must be an absolute path')
  const who = await gitIdentity(env)
  if (!who.name || !who.email) {
    return result(false, `Git has no ${!who.name ? 'user.name' : 'user.email'} configured. Set it (git config --global user.name "…" / user.email "…") and run this again; nothing was created.`)
  }
  const marker = join(dir, MARKER)
  let resuming = false
  if (await exists(dir)) {
    if (!(await stat(dir)).isDirectory()) return result(false, `${dir} exists and is not a directory`)
    const entries = await readdir(dir)
    if (entries.length) {
      if (!(await exists(marker))) return result(false, `${dir} is not empty and is not an unfinished creation; nothing was changed. Choose another destination, or use register for an existing project.`)
      if (!o.resume) return result(false, `${dir} holds an unfinished creation (${MARKER}). Run the same creation again with resume to continue it; nothing was changed.`, { resumable: true })
      resuming = true
    }
  }

  try {
    await mkdir(join(dir, '.local'), { recursive: true })
    await writeFile(marker, `${JSON.stringify({ id: o.id, devdocsSource: o.devdocsSource ?? null, startedAt: new Date().toISOString() }, null, 2)}\n`)
    step('destination', resuming ? 'kept' : 'done', resuming ? `continuing in ${dir}` : `created ${dir}`)
    stop('destination')

    // ---- devdocs source ----
    let url: string
    if (o.devdocsSource) {
      const src = o.devdocsSource.trim()
      url = isUrl(src) ? src : posix(relative(dir, resolve(dir, src)))
      if (!isUrl(src) && !url.startsWith('.')) url = `./${url}`
      step('devdocs source', 'kept', `using the existing repository ${src}`)
    } else {
      const bare = join(o.sourcesDir, `${o.id}-devdocs.git`)
      if (await exists(bare)) {
        const head = await git(bare, ['rev-parse', '--verify', '-q', 'refs/heads/main'], { env })
        if (!resuming) throw new Error(`${bare} already exists. Use it with devdocsSource, or choose another project id; nothing in it was changed.`)
        if (head.code !== 0) throw new Error(`${bare} exists but has no main branch; inspect or remove it by hand, then resume`)
        step('devdocs source', 'kept', `${bare} already exists`)
      } else {
        await mkdir(o.sourcesDir, { recursive: true })
        await run(o.sourcesDir, ['init', '--bare', '--initial-branch=main', bare])
        const work = join(o.sourcesDir, `.tmp-${o.id}-devdocs-${process.pid}`)
        await run(o.sourcesDir, ['init', '--initial-branch=main', work])
        await writeFile(join(work, 'README.md'), `# ${o.name} — devdocs\n\nRequests, plans, reports and workflow definitions of ${o.id}.\nWorkflows are in workflows/*.yaml.\n`)
        await mkdir(join(work, 'workflows'))
        await writeFile(join(work, 'workflows', '.gitkeep'), '')
        await run(work, ['add', '-A'])
        await run(work, ['commit', '-m', `Initialize devdocs for ${o.id}`])
        const sha = (await run(work, ['rev-parse', 'HEAD'])).trim()
        await run(work, ['push', bare, 'main'])
        await rm(work, { recursive: true, force: true })
        commits.push({ repository: bare, commit: sha, message: `Initialize devdocs for ${o.id}` })
        step('devdocs source', 'done', `created ${bare} with an initial commit (README.md, workflows/)`)
      }
      url = posix(relative(dir, bare))
      if (!url.startsWith('.')) url = `./${url}`
    }
    stop('devdocs source')

    // ---- root repository and files ----
    if (await exists(join(dir, '.git'))) step('root repository', 'kept', 'already a Git repository')
    else { await run(dir, ['init', '--initial-branch=main']); step('root repository', 'done', 'git init') }
    stop('root repository')

    const projectFile = join(dir, 'project.yaml')
    const current = await readTextOrNull(projectFile)
    if (current === null) {
      await writeFile(projectFile, newProjectText({ schema: PROJECT_SCHEMA, id: o.id, name: o.name.trim(), intent: o.intent, goals: o.goals.filter(g => g.trim()) }))
      step('project.yaml', 'done', 'written')
    } else {
      const parsed = parseProject(current)
      if (!parsed.ok) throw new Error(`project.yaml exists and cannot be read (${parsed.problem.message}); fix it by hand, then resume`)
      if (parsed.model.id !== o.id) throw new Error(`project.yaml exists with id "${parsed.model.id}", not "${o.id}"; nothing was replaced`)
      step('project.yaml', 'kept', 'already present; not rewritten')
    }
    const ignoreFile = join(dir, '.gitignore')
    const ignore = await readTextOrNull(ignoreFile)
    if (ignore === null) { await writeFile(ignoreFile, '.local/\n'); step('.gitignore', 'done', 'written with .local/') }
    else if (!ignore.split('\n').some(l => /^\/?\.local\/?\s*$/.test(l))) { await writeFile(ignoreFile, `${ignore}${ignore.endsWith('\n') || !ignore ? '' : '\n'}.local/\n`); step('.gitignore', 'done', 'added .local/') }
    else step('.gitignore', 'kept', 'already ignores .local/')
    stop('files')

    // ---- devdocs submodule ----
    const ws = new Workspace({ id: o.id, label: o.name, host: 'this machine', path: dir })
    if ((await ws.submodulePaths()).some(s => s.path === 'devdocs')) {
      step('devdocs submodule', 'kept', 'already in .gitmodules')
    } else {
      if (await exists(join(dir, 'devdocs'))) throw new Error('devdocs/ exists but is not a submodule; move it aside by hand (nothing was deleted), then resume')
      await run(dir, ['submodule', 'add', '--', url, 'devdocs'])
      step('devdocs submodule', 'done', `git submodule add ${url} devdocs`)
    }
    if (!(await exists(join(dir, 'devdocs', 'workflows')))) {
      await mkdir(join(dir, 'devdocs', 'workflows'), { recursive: true })
      step('devdocs/workflows', 'done', 'created (empty; the devdocs source had no workflows/)')
    }
    stop('devdocs submodule')

    // ---- initial commit ----
    await run(dir, ['add', '--', 'project.yaml', '.gitignore', '.gitmodules', 'devdocs'])
    const staged = await git(dir, ['diff', '--cached', '--quiet'], { env })
    if (staged.code === 1) {
      const message = `Create project ${o.id}`
      await run(dir, ['commit', '-m', message])
      const sha = (await run(dir, ['rev-parse', 'HEAD'])).trim()
      commits.push({ repository: dir, commit: sha, message })
      step('initial commit', 'done', `${message} (${sha.slice(0, 7)})`)
    } else step('initial commit', 'kept', 'nothing left to commit')
    stop('initial commit')

    // ---- registration ----
    const reg = await registerWorkspace(o.registryFile, dir, { id: o.workspaceId ?? o.id, label: o.name })
    if (!reg.ok) throw new Error(`registration refused: ${reg.message}`)
    step('registration', reg.status === 'registered' ? 'done' : 'kept', reg.message)
    await rm(marker, { force: true })
    return result(true, `Created ${o.id} in ${dir} and registered it as workspace "${reg.registration!.id}".`, { workspace: reg.registration!.id, diagnostics: reg.diagnostics })
  } catch (e) {
    const done = steps.map(s => s.name).join(', ') || 'nothing'
    steps.push({ name: 'stopped', status: 'failed', detail: (e as Error).message })
    return result(false, `Creation stopped: ${(e as Error).message}. Finished so far: ${done}. Nothing was rolled back; fix the cause and run the same creation with resume.`, { resumable: await exists(marker) })
  }
}
