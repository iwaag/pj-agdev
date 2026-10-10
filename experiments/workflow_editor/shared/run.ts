// Workflow runs (ag.workflow-run.v1): the one reducer that turns a run's
// history into its current state, readiness and the execution summary.
// Shared by the service, the CLI and the browser; it touches no files.
// See docs/runs.md for the contract.
import { canonicalJson } from './canonical.ts'
import { ID_PATTERN, normalizeRepoPath, type Edge } from './model.ts'

export const RUN_SCHEMA = 'ag.workflow-run.v1'
export const RUN_ID = /^run-[a-z0-9][a-z0-9_.-]{0,59}$/
export const QUESTION_ID = /^q[0-9]{1,6}$/
export const NODE_STATES = ['pending', 'running', 'waiting', 'completed', 'failed', 'cancelled'] as const
export type NodeState = typeof NODE_STATES[number]
export const EXECUTION_STATES = ['not-started', 'in-progress', 'stopped', 'completed', 'cancelled'] as const
export type ExecutionState = typeof EXECUTION_STATES[number]

export class RunError extends Error {
  code: string
  constructor(code: string, message: string) { super(message); this.code = code }
}
const fail = (code: string, message: string): never => { throw new RunError(code, message) }

// ---- record shape -------------------------------------------------------------

export interface RunRef { workflow: string; run: string }
export type EntrustRef =
  | { kind: 'run'; workflow: string; run: string; node?: string }
  | { kind: 'file'; path: string }
  | { kind: 'note'; text: string }

export interface RunInput {
  kind: 'braindump' | 'request'
  file: 'braindump.md' | 'request.md'
  author?: string // braindump: the person whose words these are
  recordedBy?: string // braindump: who saved them, when not the author
  requester?: string // request: the agent that constructed it
  onBehalfOf?: string
  entrustedBy?: EntrustRef
  original?: string // run-relative file keeping the input a request was derived from
}
export interface Executor { name: string; backend: string | null }
export interface BundleEntry {
  file: string // run-relative, definition/<id>.yaml
  source: string // project-relative file it was copied from
  sha256: string // of the copied bytes
  definitionDigest: string
  approvals: { intent: string; definition: string }
}
export interface DefinitionRef { root: string; workflows: Record<string, BundleEntry>; warnings: string[] }
export interface RepoContext { path: string; head: string | null; branch: string | null; dirty: number | null }

export type WaitOn = { question: string } | { child: RunRef } | { external: string }
export interface Wait { reason: string; holder: string; on: WaitOn }
export interface Note { at: string; by: string; text: string }
export interface ChildEvidence extends RunRef { execution: ExecutionState; seq: number }
export interface NodeRecord {
  state: NodeState
  updated: string | null
  started: string | null
  ended: string | null
  wait: Wait | null
  outcome: { text: string; artifacts: string[]; child: ChildEvidence | null } | null
  failure: { reason: string; at: string; by: string } | null
  cancellation: { reason: string; at: string; by: string } | null
  notes: Note[]
  children: RunRef[]
}
// `from` gave the answer; `by` recorded it (the same unless someone relays it).
export interface Answer { text: string; from: string; by: string; at: string; via: string }
export interface Question {
  id: string
  node: string | null
  text: string
  to: string
  askedBy: string
  asked: string
  answers: Answer[]
  takenUp: { by: string; at: string; answer: number } | null
  withdrawn: { by: string; at: string; reason: string } | null
}
export interface Artifact { path: string; node: string | null; title: string; by: string; at: string }
export interface Decision { decision: 'accepted' | 'rejected'; by: string; at: string; evidence: string; note: string }
export interface Execution {
  state: ExecutionState
  counts: Record<NodeState, number>
  ready: string[]
  blocked: string[]
  active: string[]
  waiting: { node: string; holder: string; on: WaitOn }[]
  failed: string[]
}

export interface RunState {
  schema: string
  workflow: string
  run: string
  created: string
  input: RunInput
  executor: Executor
  predecessor: RunRef | null
  parent: (RunRef & { node: string }) | null
  definition: DefinitionRef
  context: { repositories: RepoContext[] }
  nodes: Record<string, NodeRecord>
  questions: Record<string, Question>
  artifacts: Artifact[]
  decisions: Decision[]
  cancelled: { reason: string; at: string; by: string } | null
  execution: Execution
  started: string | null
  ended: string | null
  updated: string
  seq: number
}

// ---- operations (history entries) ---------------------------------------------

export type OpInput =
  | { op: 'run.create'; workflow: string; run: string; input: RunInput; executor: Executor; predecessor: RunRef | null; parent: (RunRef & { node: string }) | null; definition: DefinitionRef; context: { repositories: RepoContext[] }; nodes: string[] }
  | { op: 'node.start'; node: string; reason?: string }
  | { op: 'node.progress'; node: string; text: string }
  | { op: 'node.wait'; node: string; reason: string; holder: string; external: string }
  | { op: 'node.complete'; node: string; outcome: string; artifacts?: string[]; child?: ChildEvidence }
  | { op: 'node.fail'; node: string; reason: string }
  | { op: 'node.cancel'; node: string; reason: string }
  | { op: 'node.delegate'; node: string; child: RunRef }
  | { op: 'question.ask'; question: string; node?: string; text: string; to: string }
  | { op: 'question.answer'; question: string; text: string; from?: string }
  | { op: 'question.take-up'; question: string; answer?: number }
  | { op: 'question.withdraw'; question: string; reason: string }
  | { op: 'artifact.attach'; path: string; node?: string; title?: string }
  | { op: 'run.cancel'; reason: string }
  | { op: 'run.decide'; decision: 'accepted' | 'rejected'; evidence: string; note?: string }

export const OPS = ['run.create', 'node.start', 'node.progress', 'node.wait', 'node.complete', 'node.fail', 'node.cancel', 'node.delegate',
  'question.ask', 'question.answer', 'question.take-up', 'question.withdraw', 'artifact.attach', 'run.cancel', 'run.decide'] as const

// What one entry changed, kept in the entry for readers of the raw history.
export interface Change {
  nodes?: Record<string, [NodeState | null, NodeState]>
  question?: [string | null, string]
  execution?: [ExecutionState | null, ExecutionState]
}
export type HistoryEntry = OpInput & { seq: number; at: string; by: string; via: string; change: Change }
export interface RunRecord extends RunState { history: HistoryEntry[] }

// The graph the run follows: the root workflow of its bundle.
export interface RunGraph { nodes: Record<string, { type: string; workflow?: string }>; edges: Edge[] }

// ---- readiness and summary ------------------------------------------------------

export function predecessors(graph: RunGraph): Map<string, string[]> {
  const preds = new Map<string, string[]>(Object.keys(graph.nodes).map(id => [id, []]))
  for (const e of graph.edges) {
    const list = preds.get(e.to)
    if (list && e.from in graph.nodes && e.from !== e.to && !list.includes(e.from)) list.push(e.from)
  }
  return preds
}

// Ready: pending with every predecessor completed. Blocked: pending behind a
// failed, cancelled or blocked predecessor (failure never satisfies a dependency).
export function readiness(nodes: Record<string, { state: NodeState }>, graph: RunGraph): { ready: string[]; blocked: string[] } {
  const preds = predecessors(graph)
  const memo = new Map<string, boolean>()
  const isBlocked = (id: string, seen = new Set<string>()): boolean => {
    if (memo.has(id)) return memo.get(id)!
    if (seen.has(id)) return false
    seen.add(id)
    const b = (preds.get(id) ?? []).some(p => ['failed', 'cancelled'].includes(nodes[p]?.state) || (nodes[p]?.state === 'pending' && isBlocked(p, seen)))
    memo.set(id, b)
    return b
  }
  const ready: string[] = [], blocked: string[] = []
  for (const id of Object.keys(graph.nodes).sort()) {
    if (nodes[id]?.state !== 'pending') continue
    if ((preds.get(id) ?? []).every(p => nodes[p]?.state === 'completed')) ready.push(id)
    else if (isBlocked(id)) blocked.push(id)
  }
  return { ready, blocked }
}

export function summarize(s: Pick<RunState, 'nodes' | 'cancelled'>, graph: RunGraph): Execution {
  const counts = Object.fromEntries(NODE_STATES.map(k => [k, 0])) as Record<NodeState, number>
  const ids = Object.keys(s.nodes).sort()
  for (const id of ids) counts[s.nodes[id].state]++
  const { ready, blocked } = readiness(s.nodes, graph)
  const active = ids.filter(id => s.nodes[id].state === 'running')
  const waiting = ids.filter(id => s.nodes[id].state === 'waiting').map(id => ({ node: id, holder: s.nodes[id].wait?.holder ?? '', on: s.nodes[id].wait?.on ?? { external: '' } }))
  const failed = ids.filter(id => s.nodes[id].state === 'failed')
  let state: ExecutionState
  if (s.cancelled) state = 'cancelled'
  else if (ids.length > 0 && counts.completed === ids.length) state = 'completed'
  else if (counts.pending === ids.length) state = 'not-started'
  else if (active.length || waiting.length || ready.length) state = 'in-progress'
  else state = 'stopped'
  return { state, counts, ready, blocked, active, waiting, failed }
}

// Who holds the next move on a waiting node, as the view states it.
export function holderOf(s: RunState, node: string): string {
  const w = s.nodes[node]?.wait
  if (!w) return ''
  if ('question' in w.on) {
    const q = s.questions[w.on.question]
    if (q && q.answers.length && !q.takenUp && !q.withdrawn) return `${s.executor.name} (answer recorded, not yet taken up)`
  }
  return w.holder
}

export function questionState(q: Question): 'open' | 'answered' | 'taken-up' | 'withdrawn' {
  return q.withdrawn ? 'withdrawn' : q.takenUp ? 'taken-up' : q.answers.length ? 'answered' : 'open'
}

// ---- the reducer --------------------------------------------------------------

const text = (v: unknown, what: string): string => (typeof v === 'string' && v.trim() ? v : fail('missing', `${what} is required`))
const optText = (v: unknown, what: string): string => (v === undefined || v === null ? '' : typeof v === 'string' ? v : fail('shape', `${what} must be text`))
const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

export function validRunRef(r: unknown, what: string): RunRef {
  if (!isObj(r) || typeof r.workflow !== 'string' || !ID_PATTERN.test(r.workflow) || typeof r.run !== 'string' || !RUN_ID.test(r.run)) fail('shape', `${what} must be {workflow, run} with valid ids`)
  return { workflow: (r as RunRef).workflow, run: (r as RunRef).run }
}

export function validArtifactPath(p: unknown): string {
  const n = typeof p === 'string' ? normalizeRepoPath(p) : null
  if (!n || n === '.') fail('artifact-path', `artifact path "${String(p)}" must be project-relative, inside the project`)
  return n!
}

function emptyNode(): NodeRecord {
  return { state: 'pending', updated: null, started: null, ended: null, wait: null, outcome: null, failure: null, cancellation: null, notes: [], children: [] }
}

const TERMINAL: ExecutionState[] = ['completed', 'stopped', 'cancelled']

// Applies one entry. Returns the next state and what changed; throws RunError
// for an operation the current state does not allow.
export function apply(prev: RunState | null, e: HistoryEntry | (OpInput & { seq: number; at: string; by: string; via: string }), graph: RunGraph): { state: RunState; change: Change } {
  const at = text(e.at, 'at'), by = text(e.by, 'by')
  text(e.via, 'via')
  if (Number.isNaN(Date.parse(at))) fail('shape', `history ${e.seq}: "at" is not a timestamp`)
  if (e.op === 'run.create') {
    if (prev) fail('order', 'run.create may only be the first entry')
    if (!ID_PATTERN.test(e.workflow)) fail('shape', `workflow id "${e.workflow}" is invalid`)
    if (!RUN_ID.test(e.run)) fail('run-id', `run id "${e.run}" must match ${RUN_ID.source}`)
    const ids = [...(e.nodes ?? [])].sort()
    if (canonicalJson(ids) !== canonicalJson(Object.keys(graph.nodes).sort())) fail('graph', 'the nodes in run.create differ from the bundled definition')
    const nodes = Object.fromEntries(ids.map(id => [id, emptyNode()]))
    const state: RunState = {
      schema: RUN_SCHEMA, workflow: e.workflow, run: e.run, created: at,
      input: e.input, executor: e.executor, predecessor: e.predecessor ?? null, parent: e.parent ?? null,
      definition: e.definition, context: e.context,
      nodes, questions: {}, artifacts: [], decisions: [], cancelled: null,
      execution: summarize({ nodes, cancelled: null }, graph), started: null, ended: null, updated: at, seq: e.seq,
    }
    return { state, change: { execution: [null, state.execution.state] } }
  }
  if (!prev) return fail('order', 'the first history entry must be run.create')
  const s: RunState = structuredClone(prev)
  s.seq = e.seq
  s.updated = at
  const change: Change = {}
  const node = (id: unknown): NodeRecord => {
    if (typeof id !== 'string' || !(id in s.nodes)) fail('node-unknown', `node "${String(id)}" is not in this run's definition`)
    return s.nodes[id as string]
  }
  const move = (id: string, to: NodeState) => {
    const n = s.nodes[id]
    const from = change.nodes?.[id]?.[0] ?? n.state
    n.state = to
    n.updated = at
    change.nodes = { ...change.nodes, [id]: [from, to] }
  }
  const question = (id: unknown): Question => {
    if (typeof id !== 'string' || !(id in s.questions)) fail('question-unknown', `question "${String(id)}" does not exist in this run`)
    return s.questions[id as string]
  }
  const live = () => { if (s.cancelled) fail('run-cancelled', 'the run is cancelled; no further execution is recorded') }
  const ready = () => readiness(s.nodes, graph).ready

  switch (e.op) {
    case 'node.start': {
      live()
      const n = node(e.node)
      if (n.state === 'pending') {
        if (!ready().includes(e.node)) {
          const preds = predecessors(graph).get(e.node)!.filter(p => s.nodes[p].state !== 'completed')
          fail('not-ready', `node "${e.node}" is not ready: ${preds.map(p => `${p} is ${s.nodes[p].state}`).join(', ')}`)
        }
        n.started = at
        if (!s.started) s.started = at
      } else if (n.state === 'waiting') {
        n.wait = null
      } else if (n.state === 'failed') {
        text(e.reason, `resuming failed node "${e.node}": a reason`)
        n.failure = null; n.ended = null
      } else fail('state', `node "${e.node}" is ${n.state}; start applies to pending (ready), waiting or failed nodes`)
      if (e.reason) n.notes.push({ at, by, text: e.reason })
      move(e.node, 'running')
      break
    }
    case 'node.progress': {
      live()
      const n = node(e.node)
      if (n.state !== 'running' && n.state !== 'waiting') fail('state', `node "${e.node}" is ${n.state}; progress notes apply to running or waiting nodes`)
      n.notes.push({ at, by, text: text(e.text, 'the note text') })
      n.updated = at
      break
    }
    case 'node.wait': {
      live()
      const n = node(e.node)
      if (n.state !== 'running') fail('state', `node "${e.node}" is ${n.state}; only a running node can start waiting`)
      n.wait = { reason: text(e.reason, 'the reason'), holder: text(e.holder, 'the holder of the next move'), on: { external: text(e.external, 'the external result reference') } }
      move(e.node, 'waiting')
      break
    }
    case 'node.delegate': {
      live()
      const n = node(e.node)
      const def = graph.nodes[e.node]
      if (def.type !== 'delegate') fail('not-delegate', `node "${e.node}" is a ${def.type} node; only delegate nodes delegate`)
      if (n.state !== 'running') fail('state', `node "${e.node}" is ${n.state}; start it before delegating`)
      const child = validRunRef(e.child, 'child')
      if (child.workflow !== def.workflow) fail('child-workflow', `node "${e.node}" delegates to "${def.workflow}", not "${child.workflow}"`)
      n.children.push(child)
      n.wait = { reason: `delegated to ${child.workflow}/${child.run}`, holder: `run ${child.workflow}/${child.run}`, on: { child } }
      move(e.node, 'waiting')
      break
    }
    case 'node.complete': {
      live()
      const n = node(e.node)
      if (n.state !== 'running') fail('state', `node "${e.node}" is ${n.state}; only a running node completes${n.state === 'waiting' ? ' (resume it with start first)' : ''}`)
      const artifacts = (e.artifacts ?? []).map(validArtifactPath)
      let child: ChildEvidence | null = null
      if (graph.nodes[e.node].type === 'delegate') {
        const last = n.children.at(-1)
        if (!last) fail('child-missing', `delegate node "${e.node}" has no child run; delegate first`)
        if (!e.child || canonicalJson(validRunRef(e.child, 'child')) !== canonicalJson(last)) fail('child-evidence', `completing "${e.node}" needs the state of its child run ${last!.workflow}/${last!.run}`)
        if (e.child!.execution !== 'completed') fail('child-not-completed', `child run ${last!.workflow}/${last!.run} is ${e.child!.execution}, not completed`)
        child = { ...last!, execution: e.child!.execution, seq: e.child!.seq }
      }
      n.outcome = { text: text(e.outcome, 'the outcome'), artifacts, child }
      n.ended = at
      for (const path of artifacts) s.artifacts.push({ path, node: e.node, title: '', by, at })
      move(e.node, 'completed')
      break
    }
    case 'node.fail': {
      live()
      const n = node(e.node)
      if (n.state !== 'running' && n.state !== 'waiting') fail('state', `node "${e.node}" is ${n.state}; only running or waiting nodes fail`)
      n.failure = { reason: text(e.reason, 'the reason'), at, by }
      n.wait = null; n.ended = at
      move(e.node, 'failed')
      break
    }
    case 'node.cancel': {
      live()
      const n = node(e.node)
      if (n.state === 'completed' || n.state === 'cancelled') fail('state', `node "${e.node}" is ${n.state}; it cannot be cancelled`)
      n.cancellation = { reason: text(e.reason, 'the reason'), at, by }
      n.wait = null; n.ended = at
      move(e.node, 'cancelled')
      break
    }
    case 'question.ask': {
      live()
      if (!QUESTION_ID.test(e.question)) fail('shape', `question id "${e.question}" must match ${QUESTION_ID.source}`)
      if (e.question in s.questions) fail('question-exists', `question ${e.question} already exists`)
      const q: Question = { id: e.question, node: e.node ?? null, text: text(e.text, 'the question'), to: text(e.to, 'to whom the question is addressed'), askedBy: by, asked: at, answers: [], takenUp: null, withdrawn: null }
      if (e.node !== undefined && e.node !== null) {
        const n = node(e.node)
        if (n.state !== 'running') fail('state', `node "${e.node}" is ${n.state}; a question waits from a running node${n.state === 'waiting' ? ' (it already waits on something)' : ''}`)
        n.wait = { reason: `question ${q.id}`, holder: q.to, on: { question: q.id } }
        move(e.node, 'waiting')
      }
      s.questions[q.id] = q
      change.question = [null, q.id]
      break
    }
    case 'question.answer': {
      const q = question(e.question)
      if (q.withdrawn) fail('question-closed', `question ${q.id} was withdrawn`)
      if (q.takenUp) fail('question-closed', `the answer to ${q.id} was already taken up; ask a new question`)
      q.answers.push({ text: text(e.text, 'the answer'), from: optText(e.from, 'from').trim() || by, by, at, via: e.via })
      change.question = [q.id, 'answered']
      if (q.node) s.nodes[q.node].updated = at
      break
    }
    case 'question.take-up': {
      live()
      const q = question(e.question)
      if (q.withdrawn || q.takenUp) fail('question-closed', `question ${q.id} is ${questionState(q)}`)
      if (!q.answers.length) fail('no-answer', `question ${q.id} has no answer to take up`)
      const index = e.answer ?? q.answers.length - 1
      if (!Number.isInteger(index) || index < 0 || index >= q.answers.length) fail('shape', `question ${q.id} has no answer ${index}`)
      q.takenUp = { by, at, answer: index }
      change.question = [q.id, 'taken-up']
      resumeFrom(q)
      break
    }
    case 'question.withdraw': {
      live()
      const q = question(e.question)
      if (q.withdrawn || q.takenUp) fail('question-closed', `question ${q.id} is ${questionState(q)}`)
      q.withdrawn = { by, at, reason: text(e.reason, 'the reason') }
      change.question = [q.id, 'withdrawn']
      resumeFrom(q)
      break
    }
    case 'artifact.attach': {
      const path = validArtifactPath(e.path)
      if (e.node !== undefined && e.node !== null) node(e.node).updated = at
      s.artifacts.push({ path, node: e.node ?? null, title: optText(e.title, 'title'), by, at })
      break
    }
    case 'run.cancel': {
      live()
      const reason = text(e.reason, 'the reason')
      s.cancelled = { reason, at, by }
      for (const [id, n] of Object.entries(s.nodes)) {
        if (n.state === 'pending' || n.state === 'running' || n.state === 'waiting') {
          n.cancellation = { reason: `run cancelled: ${reason}`, at, by }
          n.wait = null; n.ended = at
          move(id, 'cancelled')
        }
      }
      break
    }
    case 'run.decide': {
      if (e.decision !== 'accepted' && e.decision !== 'rejected') fail('shape', 'decision must be accepted or rejected')
      if (e.decision === 'accepted' && prev.execution.state !== 'completed') fail('not-completed', `the execution is ${prev.execution.state}; only a completed execution can be accepted`)
      s.decisions.push({ decision: e.decision, by, at, evidence: text(e.evidence, 'the evidence'), note: optText(e.note, 'note') })
      break
    }
    default:
      fail('op-unknown', `unknown operation "${(e as { op: string }).op}"`)
  }

  function resumeFrom(q: Question) {
    if (!q.node) return
    const n = s.nodes[q.node]
    if (n.state === 'waiting' && n.wait && 'question' in n.wait.on && n.wait.on.question === q.id) {
      n.wait = null
      move(q.node, 'running')
    }
  }

  const before = prev.execution.state
  s.execution = summarize(s, graph)
  if (s.execution.state !== before) {
    change.execution = [before, s.execution.state]
    s.ended = TERMINAL.includes(s.execution.state) ? at : null
  }
  return { state: s, change }
}

// Replays a whole history. Throws RunError naming the entry that fails.
export function replay(history: unknown[], graph: RunGraph): { state: RunState; changes: Change[] } {
  let state: RunState | null = null
  const changes: Change[] = []
  history.forEach((raw, i) => {
    if (!isObj(raw)) fail('shape', `history entry ${i + 1} is not an object`)
    const e = raw as HistoryEntry
    if (e.seq !== i + 1) fail('sequence', `history entry ${i + 1} has seq ${String(e.seq)}; expected ${i + 1}`)
    if (!(OPS as readonly string[]).includes(e.op)) fail('op-unknown', `history ${e.seq}: unknown operation "${String(e.op)}"`)
    try {
      const r = apply(state, e, graph)
      state = r.state
      changes.push(r.change)
    } catch (err) {
      if (err instanceof RunError) throw new RunError(err.code, `history ${e.seq} (${e.op}): ${err.message}`)
      throw new RunError('shape', `history ${e.seq} (${e.op}): ${(err as Error).message}`)
    }
  })
  if (!state) fail('empty', 'the history is empty')
  return { state: state!, changes }
}

export function stateOf(record: RunRecord): RunState {
  const { history: _, ...state } = record
  return state
}

// Reads a parsed run.json against its graph: the history must replay and the
// stored state and per-entry changes must equal the replay.
export function checkRecord(raw: unknown, graph: RunGraph): { ok: true; record: RunRecord } | { ok: false; code: string; message: string } {
  try {
    if (!isObj(raw)) fail('shape', 'run.json must be an object')
    const r = raw as Record<string, unknown>
    if (r.schema !== RUN_SCHEMA) fail('schema', `schema is "${String(r.schema)}"; expected ${RUN_SCHEMA}`)
    if (!Array.isArray(r.history)) fail('shape', 'history must be a list')
    const { state, changes } = replay(r.history as unknown[], graph)
    const record = raw as unknown as RunRecord
    if (canonicalJson(stateOf(record)) !== canonicalJson(state)) {
      const keys = new Set([...Object.keys(state), ...Object.keys(stateOf(record))])
      const differ = [...keys].filter(k => canonicalJson((state as unknown as Record<string, unknown>)[k] ?? null) !== canonicalJson((stateOf(record) as unknown as Record<string, unknown>)[k] ?? null))
      fail('inconsistent', `the stored state differs from its history in: ${differ.join(', ')}`)
    }
    record.history.forEach((e, i) => {
      if (canonicalJson(e.change ?? null) !== canonicalJson(changes[i])) fail('inconsistent', `history ${e.seq}: the recorded change differs from what the operation does`)
    })
    return { ok: true, record }
  } catch (e) {
    if (e instanceof RunError) return { ok: false, code: e.code, message: e.message }
    return { ok: false, code: 'shape', message: (e as Error).message }
  }
}

// Appends one operation: the next record, written by the caller in one
// atomic replacement. `expectSeq` refuses an operation based on an outdated view.
export function operate(record: RunRecord | null, input: OpInput, ctx: { at: string; by: string; via: string; graph: RunGraph; expectSeq?: number }): RunRecord {
  const seq = (record?.seq ?? 0) + 1
  if (ctx.expectSeq !== undefined && ctx.expectSeq !== (record?.seq ?? 0)) {
    fail('outdated', `the run changed since it was read (now at ${record?.seq ?? 0}, expected ${ctx.expectSeq}); reload and retry`)
  }
  const entry = { ...input, seq, at: ctx.at, by: ctx.by, via: ctx.via } as HistoryEntry
  const { state, change } = apply(record ? stateOf(record) : null, entry, ctx.graph)
  entry.change = change
  return { ...state, history: [...(record?.history ?? []), entry] }
}

export const runKey = (r: RunRef) => `${r.workflow}/${r.run}`
