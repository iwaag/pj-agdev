// p3/pre1 step 2: workflow runs — the reducer (readiness, joins, failure,
// questions, summary, replay checks) and the files (snapshot closure,
// authorship, collisions, delegation, malformed records, Git history).
import { before, after, test } from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, readFile, rename, rm, unlink, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import {
  checkRecord, operate, replay, RunError, summarize, type OpInput, type RunGraph, type RunRecord,
} from '../shared/run.ts'
import { createProject } from '../server/create.ts'
import { gitOk } from '../server/git.ts'
import { loadRegistry } from '../server/registry.ts'
import { checkRun, createRun, delegate, listRuns, runOp, runResponse, readRun, type CreateRunOptions } from '../server/runs.ts'
import { RequestError, Workspace } from '../server/workspace.ts'
import { main } from '../cli/wfe.ts'

// ---- reducer -----------------------------------------------------------------------

// a → b, a → c, (b, c) → j: a branch and a join.
const G: RunGraph = {
  nodes: { a: { type: 'study' }, b: { type: 'do' }, c: { type: 'talk' }, j: { type: 'do' } },
  edges: [{ from: 'a', to: 'b' }, { from: 'a', to: 'c' }, { from: 'b', to: 'j' }, { from: 'c', to: 'j' }],
}
let clock = Date.parse('2026-10-10T00:00:00.000Z')
const tick = () => new Date(clock += 1000).toISOString()
const create = (graph = G): RunRecord => operate(null, {
  op: 'run.create', workflow: 'w', run: 'run-001', nodes: Object.keys(graph.nodes),
  input: { kind: 'braindump', file: 'braindump.md', author: 'Person' }, executor: { name: 'Agent', backend: null },
  predecessor: null, parent: null, definition: { root: 'w', workflows: {}, warnings: [] }, context: { repositories: [] },
}, { at: tick(), by: 'Agent', via: 'test', graph })
const step = (r: RunRecord, op: OpInput, by = 'Agent', graph = G) => operate(r, op, { at: tick(), by, via: 'test', graph })
const refused = (f: () => unknown, code: string) => assert.throws(f, (e: unknown) => e instanceof RunError && e.code === code)

test('readiness follows completed predecessors; a join waits for every branch', () => {
  let r = create()
  assert.equal(r.execution.state, 'not-started')
  assert.deepEqual(r.execution.ready, ['a'])
  refused(() => step(r, { op: 'node.start', node: 'b' }), 'not-ready')
  r = step(r, { op: 'node.start', node: 'a' })
  assert.equal(r.execution.state, 'in-progress')
  assert.ok(r.started)
  r = step(r, { op: 'node.complete', node: 'a', outcome: 'surveyed' })
  assert.deepEqual(r.execution.ready, ['b', 'c'])
  r = step(r, { op: 'node.start', node: 'b' })
  r = step(r, { op: 'node.start', node: 'c' })
  assert.deepEqual(r.execution.active, ['b', 'c'], 'both branches are visible as active')
  r = step(r, { op: 'node.complete', node: 'b', outcome: 'built' })
  refused(() => step(r, { op: 'node.start', node: 'j' }), 'not-ready')
  assert.deepEqual(r.execution.ready, [])
  r = step(r, { op: 'node.complete', node: 'c', outcome: 'agreed' })
  assert.deepEqual(r.execution.ready, ['j'])
  r = step(r, { op: 'node.start', node: 'j' })
  r = step(r, { op: 'node.complete', node: 'j', outcome: 'joined' })
  assert.equal(r.execution.state, 'completed')
  assert.ok(r.ended)
  assert.equal(r.decisions.length, 0, 'completion is not acceptance')
})

test('failure and cancellation never satisfy a dependency, and a failure stays visible beside other work', () => {
  let r = create()
  r = step(r, { op: 'node.start', node: 'a' })
  r = step(r, { op: 'node.complete', node: 'a', outcome: 'ok' })
  r = step(r, { op: 'node.start', node: 'b' })
  r = step(r, { op: 'node.start', node: 'c' })
  r = step(r, { op: 'node.fail', node: 'b', reason: 'tests do not pass' })
  assert.equal(r.execution.state, 'in-progress', 'c still runs')
  assert.deepEqual(r.execution.failed, ['b'])
  assert.deepEqual(r.execution.active, ['c'])
  r = step(r, { op: 'node.complete', node: 'c', outcome: 'ok' })
  assert.deepEqual(r.execution.blocked, ['j'])
  refused(() => step(r, { op: 'node.start', node: 'j' }), 'not-ready')
  assert.equal(r.execution.state, 'stopped')
  refused(() => step(r, { op: 'node.start', node: 'b' }), 'missing') // a failed node resumes only with a reason
  const resumed = step(r, { op: 'node.start', node: 'b', reason: 'fixed the fixture' })
  assert.equal(resumed.nodes.b.state, 'running')
  assert.equal(resumed.execution.state, 'in-progress')
  assert.equal(resumed.ended, null)
  const cancelled = step(r, { op: 'node.cancel', node: 'b', reason: 'not needed' })
  assert.deepEqual(cancelled.execution.blocked, ['j'])
  refused(() => step(cancelled, { op: 'node.start', node: 'b', reason: 'x' }), 'state')
  refused(() => step(r, { op: 'run.decide', decision: 'accepted', evidence: 'x' }, 'Person'), 'not-completed')
})

test('a talk node keeps its question; answer, take-up and completion are separate records', () => {
  let r = create()
  r = step(r, { op: 'node.start', node: 'a' })
  r = step(r, { op: 'node.complete', node: 'a', outcome: 'ok' })
  r = step(r, { op: 'node.start', node: 'c' })
  r = step(r, { op: 'question.ask', question: 'q1', node: 'c', text: 'Which genre?', to: 'Person' })
  r = step(r, { op: 'question.ask', question: 'q2', text: 'Unrelated: preferred name?', to: 'Person' })
  assert.equal(r.nodes.c.state, 'waiting')
  assert.deepEqual(r.execution.waiting, [{ node: 'c', holder: 'Person', on: { question: 'q1' } }])
  refused(() => step(r, { op: 'question.ask', question: 'q3', node: 'c', text: 'again?', to: 'Person' }), 'state')
  r = step(r, { op: 'question.answer', question: 'q2', text: 'Call me P.' }, 'Person')
  assert.equal(r.nodes.c.state, 'waiting', 'an answer to another question leaves it waiting')
  r = step(r, { op: 'question.answer', question: 'q1', text: 'Strategy.' }, 'Person')
  assert.equal(r.nodes.c.state, 'waiting', 'recording an answer is not taking it up')
  assert.equal(r.questions.q1.answers[0].from, 'Person')
  const relayed = step(r, { op: 'question.answer', question: 'q1', text: 'Real-time strategy.', from: 'Person' }, 'Agent')
  assert.deepEqual([relayed.questions.q1.answers[1].from, relayed.questions.q1.answers[1].by], ['Person', 'Agent'])
  r = step(r, { op: 'question.take-up', question: 'q1' })
  assert.equal(r.nodes.c.state, 'running', 'taking up resumes the node')
  assert.equal(r.questions.q1.takenUp?.answer, 0)
  assert.notEqual(r.nodes.c.state, 'completed', 'taking up is not completing')
  r = step(r, { op: 'node.complete', node: 'c', outcome: 'genre agreed' })
  assert.equal(r.nodes.c.state, 'completed')
  refused(() => step(r, { op: 'question.answer', question: 'q1', text: 'late' }, 'Person'), 'question-closed')
  // Withdrawal closes a question without an answer.
  let w = create()
  w = step(w, { op: 'node.start', node: 'a' })
  w = step(w, { op: 'question.ask', question: 'q1', node: 'a', text: 'Need X?', to: 'Person' })
  w = step(w, { op: 'question.withdraw', question: 'q1', reason: 'found it in the docs' })
  assert.equal(w.nodes.a.state, 'running')
  assert.equal(w.questions.q1.answers.length, 0)
})

test('old timestamps alone change nothing', () => {
  clock = Date.parse('2026-01-01T00:00:00.000Z')
  let r = create()
  r = step(r, { op: 'node.start', node: 'a' })
  r = step(r, { op: 'question.ask', question: 'q1', node: 'a', text: '?', to: 'Person' })
  clock = Date.now()
  const after = summarize(r, G)
  assert.equal(r.nodes.a.state, 'waiting')
  assert.equal(after.state, 'in-progress')
  assert.ok(Date.now() - Date.parse(r.updated) > 1000 * 3600 * 24 * 30)
  assert.equal(checkRecord(JSON.parse(JSON.stringify(r)), G).ok, true)
})

test('replay is the authority: edited state, edited changes and gaps are inconsistent', () => {
  let r = create()
  r = step(r, { op: 'node.start', node: 'a' })
  r = step(r, { op: 'node.complete', node: 'a', outcome: 'ok' })
  assert.equal(checkRecord(structuredClone(r), G).ok, true)
  const state = structuredClone(r); state.nodes.b.state = 'completed'
  const s1 = checkRecord(state, G)
  assert.ok(!s1.ok && s1.code === 'inconsistent' && /nodes/.test(s1.message))
  const changed = structuredClone(r); changed.history[1].change = {}
  assert.equal((checkRecord(changed, G) as { code: string }).code, 'inconsistent')
  const gap = structuredClone(r); gap.history.splice(1, 1)
  assert.equal((checkRecord(gap, G) as { code: string }).code, 'sequence')
  const illegal = structuredClone(r); (illegal.history[1] as { node: string }).node = 'j'
  assert.equal((checkRecord(illegal, G) as { code: string }).code, 'not-ready')
  assert.equal((checkRecord({ schema: 'x' }, G) as { code: string }).code, 'schema')
  const { state: replayed } = replay(r.history, G)
  assert.equal(replayed.seq, 3)
  assert.throws(() => operate(r, { op: 'node.start', node: 'b' }, { at: tick(), by: 'P', via: 'test', graph: G, expectSeq: 2 }), (e: unknown) => (e as RunError).code === 'outdated')
})

test('run cancellation cancels open nodes in the same entry and stops further records', () => {
  let r = create()
  r = step(r, { op: 'node.start', node: 'a' })
  r = step(r, { op: 'run.cancel', reason: 'priorities changed' }, 'Person')
  assert.equal(r.execution.state, 'cancelled')
  assert.deepEqual(Object.values(r.nodes).map(n => n.state), ['cancelled', 'cancelled', 'cancelled', 'cancelled'])
  assert.deepEqual(Object.keys(r.history.at(-1)!.change.nodes!).sort(), ['a', 'b', 'c', 'j'])
  refused(() => step(r, { op: 'node.start', node: 'b' }), 'run-cancelled')
  const rejected = step(r, { op: 'run.decide', decision: 'rejected', evidence: 'cancelled' }, 'Person')
  assert.equal(rejected.decisions[0].decision, 'rejected')
})

// ---- files -------------------------------------------------------------------------

let root = '', dir = '', registry = ''
let ws: Workspace

const wf = (id: string, nodes: string, edges: string) => `schema: ag.workflow.v1
id: ${id}
name: ${id}
intent: |
  Test workflow ${id}.
repositories:
  docs: {path: devdocs, access: editable}
nodes:
${nodes}
edges:
${edges}
`
const node = (id: string, type: string, extra = '') => `  ${id}:\n    type: ${type}\n    description: ${id} step\n${extra}`
const SHIP = wf('ship', [node('survey', 'study'), node('build', 'do'), node('ask', 'talk'), node('handoff', 'delegate', '    workflow: sub\n'), node('join', 'do')].join(''),
  '  - {from: survey, to: build}\n  - {from: survey, to: ask}\n  - {from: survey, to: handoff}\n  - {from: build, to: join}\n  - {from: ask, to: join}\n  - {from: handoff, to: join}')
const SUB = wf('sub', [node('prepare', 'do'), node('deeper', 'delegate', '    workflow: leaf\n')].join(''), '  - {from: prepare, to: deeper}')
const LEAF = wf('leaf', node('only', 'do'), '  []')
const braindump = (text = 'I want a small game.'): CreateRunOptions['input'] => ({ kind: 'braindump', text, author: 'Test Person', recordedBy: 'Omni Agent' })
const base = (o: Partial<CreateRunOptions> = {}): CreateRunOptions => ({ workflow: 'ship', input: braindump(), executor: { name: 'Omni Agent', backend: 'test-harness' }, by: 'Omni Agent', via: 'cli', ...o })
const gitDocs = (args: string[]) => gitOk(join(dir, 'devdocs'), args)

before(async () => {
  root = await mkdtemp(join(tmpdir(), 'wfe-runs-'))
  await writeFile(join(root, 'gitconfig'), '[user]\n\tname = Test Person\n\temail = t@example.invalid\n')
  process.env.GIT_CONFIG_GLOBAL = join(root, 'gitconfig')
  registry = join(root, 'registry.json')
  dir = join(root, 'pj-r')
  const r = await createProject({ dir, id: 'r', name: 'R', intent: 'x', goals: ['g'], sourcesDir: join(root, 'sources'), registryFile: registry })
  assert.ok(r.ok, r.message)
  for (const [id, text] of [['ship', SHIP], ['sub', SUB], ['leaf', LEAF]]) await writeFile(join(dir, 'devdocs', 'workflows', `${id}.yaml`), text)
  ws = new Workspace((await loadRegistry(registry)).workspaces[0])
})
after(async () => { await rm(root, { recursive: true, force: true }) })

test('creation snapshots the workflow and its transitive delegates, with authorship and context', async () => {
  const c = await createRun(ws, base())
  assert.equal(c.dir, 'devdocs/ship/runs/run-001')
  assert.deepEqual(Object.keys(c.record.definition.workflows).sort(), ['leaf', 'ship', 'sub'])
  for (const id of ['ship', 'sub', 'leaf']) assert.equal(await readFile(join(dir, c.dir, 'definition', `${id}.yaml`), 'utf8'), await readFile(join(dir, 'devdocs', 'workflows', `${id}.yaml`), 'utf8'))
  assert.deepEqual(c.record.input, { kind: 'braindump', file: 'braindump.md', author: 'Test Person', recordedBy: 'Omni Agent' })
  assert.equal(await readFile(join(dir, c.dir, 'braindump.md'), 'utf8'), 'I want a small game.')
  assert.deepEqual(c.record.executor, { name: 'Omni Agent', backend: 'test-harness' })
  assert.deepEqual(c.record.context.repositories.map(r => r.path).sort(), ['.', 'devdocs'])
  assert.equal(c.record.definition.workflows.ship.approvals.definition, 'unapproved')
  assert.ok(!JSON.stringify(c.record).includes(root), 'no machine paths in the record')
  const again = await readRun(ws, c.ref)
  assert.ok(again.record, again.problem?.message)
  assert.equal((await createRun(ws, base())).ref.run, 'run-002', 'the next number')
})

test('requests keep their requester and entrusting reference; collisions never overwrite', async () => {
  const req = await createRun(ws, base({ name: 'run-derived', input: { kind: 'request', text: 'Build the game, focusing on bots.', requester: 'Omni Agent', entrustedBy: { kind: 'note', text: 'VS Code conversation 2026-10-10' }, onBehalfOf: 'Test Person', original: 'raw words of the person' } }))
  assert.deepEqual(req.record.input, { kind: 'request', file: 'request.md', requester: 'Omni Agent', entrustedBy: { kind: 'note', text: 'VS Code conversation 2026-10-10' }, onBehalfOf: 'Test Person', original: 'original-input.md' })
  assert.equal(req.record.input.author, undefined, 'no human author is invented for a request')
  assert.equal(await readFile(join(dir, req.dir, 'original-input.md'), 'utf8'), 'raw words of the person')
  const before = await readFile(join(dir, req.dir, 'run.json'), 'utf8')
  await assert.rejects(createRun(ws, base({ name: 'run-derived', input: braindump('other words') })), (e: unknown) => e instanceof RequestError && e.status === 409)
  assert.equal(await readFile(join(dir, req.dir, 'run.json'), 'utf8'), before)
  await assert.rejects(createRun(ws, base({ name: 'bad name' })), (e: unknown) => e instanceof RequestError && e.status === 400)
  await assert.rejects(createRun(ws, base({ input: { kind: 'braindump', text: 'x', author: '' } })), /author/)
})

test('a run keeps its captured definition when the source is edited, renamed or deleted; so do later child runs', async () => {
  const c = await createRun(ws, base({ name: 'run-fixed' }))
  const src = join(dir, 'devdocs', 'workflows')
  await writeFile(join(src, 'ship.yaml'), SHIP.replace('survey step', 'survey step, edited later'))
  let v = await runResponse(ws, c.ref)
  assert.ok(v.record)
  assert.equal(v.bundle.ship.workflow?.nodes.survey.description, 'survey step')
  assert.equal(v.sources.find(s => s.workflow === 'ship')?.status, 'changed')
  await rename(join(src, 'ship.yaml'), join(src, 'ship-renamed.yaml'))
  v = await runResponse(ws, c.ref)
  assert.equal(v.sources.find(s => s.workflow === 'ship')?.renamed, true)
  // The delegated workflow is deleted before the child run exists.
  const subText = await readFile(join(src, 'sub.yaml'), 'utf8')
  await unlink(join(src, 'sub.yaml'))
  await runOp(ws, c.ref, { op: 'node.start', node: 'survey' }, { via: 'cli' })
  await runOp(ws, c.ref, { op: 'node.complete', node: 'survey', outcome: 'done' }, { via: 'cli' })
  await runOp(ws, c.ref, { op: 'node.start', node: 'handoff' }, { via: 'cli' })
  const d = await delegate(ws, c.ref, 'handoff', { via: 'cli' })
  assert.equal(d.child.ref.workflow, 'sub')
  assert.equal(await readFile(join(dir, d.child.dir, 'definition', 'sub.yaml'), 'utf8'), subText, 'the child runs the parent\'s captured version')
  assert.deepEqual(Object.keys(d.child.record.definition.workflows).sort(), ['leaf', 'sub'], 'self-contained child bundle')
  assert.equal(d.child.record.definition.workflows.sub.source, `${c.dir}/definition/sub.yaml`)
  assert.deepEqual(d.child.record.parent, { workflow: 'ship', run: 'run-fixed', node: 'handoff' })
  assert.equal(d.child.record.input.kind, 'request')
  assert.equal(d.parent.nodes.handoff.state, 'waiting')
  assert.match(await readFile(join(dir, d.child.dir, 'request.md'), 'utf8'), /no person authored this text/)
  v = await runResponse(ws, d.child.ref)
  assert.equal(v.sources.find(s => s.workflow === 'sub')?.status, 'deleted')
  assert.equal(v.parent?.linksBack, true)
  const pv = await runResponse(ws, c.ref)
  assert.deepEqual(pv.children.map(x => [x.ref, x.node, x.execution]), [['sub/run-001', 'handoff', 'not-started']])
  // Parent completion needs the child's recorded completion.
  await runOp(ws, c.ref, { op: 'node.start', node: 'handoff' }, { via: 'cli' })
  await assert.rejects(runOp(ws, c.ref, { op: 'node.complete', node: 'handoff', outcome: 'x' }, { via: 'cli' }), /not-started, not completed/)
  await runOp(ws, d.child.ref, { op: 'node.start', node: 'prepare' }, { via: 'cli' })
  await runOp(ws, d.child.ref, { op: 'node.fail', node: 'prepare', reason: 'broken' }, { via: 'cli' })
  await assert.rejects(runOp(ws, c.ref, { op: 'node.complete', node: 'handoff', outcome: 'x' }, { via: 'cli' }), /stopped, not completed/)
  // A missing child is distinguishable.
  const childDir = join(dir, d.child.dir)
  await rename(childDir, `${childDir}-moved`)
  await assert.rejects(runOp(ws, c.ref, { op: 'node.complete', node: 'handoff', outcome: 'x' }, { via: 'cli' }), /is missing/)
  assert.equal((await runResponse(ws, c.ref)).children[0].problem, 'missing')
  await rename(`${childDir}-moved`, childDir)
  // Restore the sources for later tests.
  await rename(join(src, 'ship-renamed.yaml'), join(src, 'ship.yaml'))
  await writeFile(join(src, 'ship.yaml'), SHIP)
  await writeFile(join(src, 'sub.yaml'), subText)
})

test('a delegated chain completes bottom-up and the parent records the child as evidence', async () => {
  const c = await createRun(ws, base({ name: 'run-chain' }))
  const go = (ref: { workflow: string; run: string }, op: OpInput) => runOp(ws, ref, op, { via: 'cli' })
  await go(c.ref, { op: 'node.start', node: 'survey' })
  await go(c.ref, { op: 'node.complete', node: 'survey', outcome: 'ok' })
  await go(c.ref, { op: 'node.start', node: 'handoff' })
  const sub = (await delegate(ws, c.ref, 'handoff', { via: 'cli', name: 'run-chain' })).child.ref
  await go(sub, { op: 'node.start', node: 'prepare' })
  await go(sub, { op: 'node.complete', node: 'prepare', outcome: 'ok' })
  await go(sub, { op: 'node.start', node: 'deeper' })
  const leaf = (await delegate(ws, sub, 'deeper', { via: 'cli' })).child
  assert.deepEqual(Object.keys(leaf.record.definition.workflows), ['leaf'])
  await go(leaf.ref, { op: 'node.start', node: 'only' })
  await go(leaf.ref, { op: 'node.complete', node: 'only', outcome: 'ok' })
  await go(sub, { op: 'node.start', node: 'deeper' })
  const s = (await go(sub, { op: 'node.complete', node: 'deeper', outcome: 'leaf done' })).record
  assert.equal(s.execution.state, 'completed')
  assert.deepEqual(s.nodes.deeper.outcome?.child, { ...leaf.ref, execution: 'completed', seq: 3 })
  await go(c.ref, { op: 'node.start', node: 'handoff' })
  const p = (await go(c.ref, { op: 'node.complete', node: 'handoff', outcome: 'sub done' })).record
  assert.equal(p.nodes.handoff.state, 'completed')
  assert.equal(p.execution.state, 'in-progress', 'build, ask and join remain')
  assert.deepEqual(p.execution.ready, ['ask', 'build'])
})

test('malformed, inconsistent or tampered records are visible problems and never rewritten', async () => {
  const c = await createRun(ws, base({ name: 'run-broken' }))
  const file = join(dir, c.dir, 'run.json')
  const good = await readFile(file, 'utf8')
  await writeFile(file, good.slice(0, 50))
  let list = await listRuns(ws, 'ship')
  assert.equal(list.find(s => s.run === 'run-broken')?.problem?.code, 'malformed')
  await assert.rejects(runOp(ws, c.ref, { op: 'node.start', node: 'survey' }, { via: 'cli' }), (e: unknown) => e instanceof RequestError && e.status === 409)
  assert.equal(await readFile(file, 'utf8'), good.slice(0, 50), 'not overwritten')
  const tampered = JSON.parse(good); tampered.nodes.survey.state = 'completed'
  await writeFile(file, JSON.stringify(tampered))
  list = await listRuns(ws, 'ship')
  assert.equal(list.find(s => s.run === 'run-broken')?.problem?.code, 'inconsistent')
  await writeFile(file, good)
  await writeFile(join(dir, c.dir, 'definition', 'ship.yaml'), SHIP.replace('build step', 'sneaky'))
  const check = await checkRun(ws, c.ref)
  assert.equal(check.code, 'bundle')
  assert.match(check.problem!, /sha256/)
  await writeFile(join(dir, c.dir, 'definition', 'ship.yaml'), SHIP)
  assert.equal((await checkRun(ws, c.ref)).ok, true)
})

test('two commits each reconstruct the fixed workflow and the stage; history keeps what happened between', async () => {
  const c = await createRun(ws, base({ name: 'run-git' }))
  await runOp(ws, c.ref, { op: 'node.start', node: 'survey' }, { via: 'cli' })
  await gitDocs(['add', '-A'])
  await gitDocs(['commit', '-q', '-m', 'run-git: survey started'])
  const first = (await gitDocs(['rev-parse', 'HEAD'])).trim()
  await runOp(ws, c.ref, { op: 'node.complete', node: 'survey', outcome: 'ok' }, { via: 'cli' })
  await runOp(ws, c.ref, { op: 'node.start', node: 'build' }, { via: 'cli' })
  await runOp(ws, c.ref, { op: 'node.start', node: 'ask' }, { via: 'cli' })
  await runOp(ws, c.ref, { op: 'question.ask', question: '', node: 'ask', text: 'Which map size?', to: 'Test Person' }, { via: 'cli' })
  await gitDocs(['add', '-A'])
  await gitDocs(['commit', '-q', '-m', 'run-git: ask waits'])
  await writeFile(join(dir, 'devdocs', 'workflows', 'ship.yaml'), SHIP.replace('join step', 'join step v2'))
  const a = await runResponse(ws, c.ref, { rev: first })
  assert.ok(a.record, a.problem?.message)
  assert.equal(a.record!.seq, 2)
  assert.equal(a.record!.nodes.survey.state, 'running')
  assert.equal(a.bundle.ship.workflow?.nodes.join.description, 'join step')
  const b = await runResponse(ws, c.ref, { rev: 'HEAD' })
  assert.equal(b.record!.seq, 6)
  assert.deepEqual(b.record!.history.map(e => e.op), ['run.create', 'node.start', 'node.complete', 'node.start', 'node.start', 'question.ask'])
  assert.equal(b.record!.nodes.ask.state, 'waiting')
  assert.equal(b.record!.questions.q1.text, 'Which map size?')
  await writeFile(join(dir, 'devdocs', 'workflows', 'ship.yaml'), SHIP)
})

test('wfe run: create, show, answer and check from the command line', async () => {
  const cwd = process.cwd()
  process.chdir(dir)
  const logs: string[] = []
  const log = console.log
  console.log = (...a: unknown[]) => { logs.push(a.join(' ')) }
  try {
    await writeFile(join(root, 'bd.md'), 'The person\'s words.')
    const env = ['--registry', registry]
    assert.equal(await main(['run', 'create', 'ship', '--braindump', join(root, 'bd.md'), '--author', 'Test Person', '--executor', 'Omni Agent', '--name', 'run-cli', ...env]), 0)
    assert.equal(await main(['run', 'start', 'ship/run-cli', 'survey', ...env]), 0)
    assert.equal(await main(['run', 'start', 'run-cli', 'build', ...env]), 1, 'not ready: refused')
    assert.equal(await main(['run', 'ask', 'run-cli', 'survey', '--question', 'Scope?', '--to', 'Test Person', ...env]), 0)
    assert.equal(await main(['run', 'answer', 'run-cli', 'q1', '--answer', 'Small.', '--by', 'Test Person', '--expect-seq', '1', ...env]), 1, 'outdated view refused')
    assert.equal(await main(['run', 'answer', 'run-cli', 'q1', '--answer', 'Small.', '--by', 'Test Person', '--expect-seq', '3', ...env]), 0)
    logs.length = 0
    assert.equal(await main(['run', 'show', 'run-cli', ...env]), 0)
    const shown = logs.join('\n')
    assert.match(shown, /survey\s+waiting\s+waits: question q1; next move: Omni Agent \(answer recorded, not yet taken up\)/)
    assert.match(shown, /the words of Test Person/)
    await writeFile(join(dir, 'devdocs', 'ship', 'runs', 'run-cli', 'report1.md'), '# Survey\n')
    assert.equal(await main(['run', 'attach', 'run-cli', 'report1.md', '--node', 'survey', ...env]), 0)
    logs.length = 0
    assert.equal(await main(['run', 'list', 'ship', '--json', ...env]), 0)
    const list = JSON.parse(logs.join('\n')) as { runs: { run: string; waiting: unknown[] }[] }
    assert.deepEqual(list.runs.find(r => r.run === 'run-cli')?.waiting, [{ node: 'survey', holder: 'Omni Agent (answer recorded, not yet taken up)' }])
    const rec = JSON.parse(await readFile(join(dir, 'devdocs', 'ship', 'runs', 'run-cli', 'run.json'), 'utf8')) as RunRecord
    assert.deepEqual(rec.artifacts.map(a => a.path), ['devdocs/ship/runs/run-cli/report1.md'])
    assert.deepEqual(rec.history.map(e => e.via), ['cli', 'cli', 'cli', 'cli', 'cli'])
    assert.equal(rec.questions.q1.answers[0].by, 'Test Person')
  } finally {
    console.log = log
    process.chdir(cwd)
  }
})

test('HTTP: list, read, answer with the stale-view guard, read a report; the same operations as the CLI', async () => {
  const { createHandler } = await import('../server/api.ts')
  const { createServer } = await import('node:http')
  const handler = createHandler({ registryFile: registry, area: root, allowedOrigins: [], allowedHosts: ['127.0.0.1'] })
  const server = createServer((req, res) => void handler(req, res))
  await new Promise<void>(r => server.listen(0, '127.0.0.1', () => r()))
  const url = `http://127.0.0.1:${(server.address() as { port: number }).port}/api/workspaces/r`
  const post = (path: string, body: unknown) => fetch(`${url}${path}`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  try {
    const c = await createRun(ws, base({ name: 'run-http' }))
    await runOp(ws, c.ref, { op: 'node.start', node: 'survey' }, { via: 'cli' })
    await runOp(ws, c.ref, { op: 'question.ask', question: '', node: 'survey', text: 'Scope?', to: 'Test Person' }, { via: 'cli' })
    const list = await (await fetch(`${url}/runs`)).json() as { ref: string; waiting?: unknown[] }[]
    assert.deepEqual(list.find(r => r.ref === 'ship/run-http')?.waiting, [{ node: 'survey', holder: 'Test Person' }])
    const view = await (await fetch(`${url}/runs/ship/run-http`)).json() as { record: RunRecord; bundle: Record<string, unknown> }
    assert.equal(view.record.seq, 3)
    assert.deepEqual(Object.keys(view.bundle).sort(), ['leaf', 'ship', 'sub'])
    let r = await post('/runs/ship/run-http/ops', { op: 'question.answer', question: 'q1', text: 'Small', by: 'Test Person', expectSeq: 2 })
    assert.equal(r.status, 409)
    r = await post('/runs/ship/run-http/ops', { op: 'question.answer', question: 'q1', text: 'Small', expectSeq: 3 })
    assert.equal(r.status, 400, 'a name is required')
    r = await post('/runs/ship/run-http/ops', { op: 'question.answer', question: 'q1', text: 'Small', by: 'Test Person', expectSeq: 3 })
    assert.equal(r.status, 200)
    const rec = (await r.json() as { record: RunRecord }).record
    assert.deepEqual([rec.questions.q1.answers[0].via, rec.questions.q1.answers[0].by, rec.nodes.survey.state], ['browser', 'Test Person', 'waiting'])
    r = await post('/runs/ship/run-http/ops', { op: 'run.create', by: 'x' })
    assert.equal(r.status, 400)
    r = await post('/runs/ship/run-http/ops', { op: 'node.start', node: 'join', by: 'Test Person' })
    assert.equal(r.status, 422)
    const file = await (await fetch(`${url}/runs/ship/run-http/file?path=braindump.md`)).json() as { text: string }
    assert.equal(file.text, 'I want a small game.')
    const report = join(dir, c.dir, 'report.md')
    await writeFile(report, 'Report at the first commit.')
    await gitDocs(['add', '-A'])
    await gitDocs(['commit', '-q', '-m', 'HTTP report: first version'])
    const first = (await gitDocs(['rev-parse', 'HEAD'])).trim()
    await writeFile(report, 'Report at the second commit.')
    await gitDocs(['add', '-A'])
    await gitDocs(['commit', '-q', '-m', 'HTTP report: second version'])
    const second = (await gitDocs(['rev-parse', 'HEAD'])).trim()
    await writeFile(report, 'Uncommitted report.')
    const reportUrl = `${url}/runs/ship/run-http/file?path=report.md`
    assert.equal((await (await fetch(`${reportUrl}&rev=${first}`)).json()).text, 'Report at the first commit.')
    assert.equal((await (await fetch(`${reportUrl}&rev=${second}`)).json()).text, 'Report at the second commit.')
    assert.equal((await (await fetch(reportUrl)).json()).text, 'Uncommitted report.')
    await unlink(report)
    assert.equal((await (await fetch(`${reportUrl}&rev=${first}`)).json()).text, 'Report at the first commit.', 'history survives working-tree deletion')
    assert.equal((await fetch(reportUrl)).status, 404)
    await writeFile(join(dir, c.dir, 'later.md'), 'Only in the working tree.')
    assert.equal((await fetch(`${url}/runs/ship/run-http/file?path=later.md&rev=${first}`)).status, 404, 'missing historical files never fall back to current content')
    assert.equal((await fetch(`${reportUrl}&rev=not-a-commit`)).status, 404)
    assert.equal((await fetch(`${url}/runs/ship/run-http/file?path=../../workflows/ship.yaml&rev=${first}`)).status, 404)
    assert.equal((await fetch(`${url}/runs/ship/run-http/file?path=../../workflows/ship.yaml`)).status, 404)
    assert.equal((await fetch(`${url}/runs/ship/run-nope`)).status, 200, 'a missing run is a response with its problem')
  } finally {
    server.closeAllConnections(); server.close()
  }
})

test('watcher: run.json changes, report files and new runs are separate events; report bodies are not read', async () => {
  const { Watcher } = await import('../server/watch.ts')
  const w = new Watcher(1000, { registryFile: registry })
  const c = await createRun(ws, base({ name: 'run-watch' }))
  const s0 = await w.snapshot({ ws, snapshot: null })
  await runOp(ws, c.ref, { op: 'node.start', node: 'survey' }, { via: 'cli' })
  const s1 = await w.snapshot({ ws, snapshot: s0 })
  assert.deepEqual(w.diff('r', s0, s1).map(e => [e.kind, e.run]), [['run', 'ship/run-watch']])
  await writeFile(join(dir, c.dir, 'report1.md'), '# r\n')
  const s2 = await w.snapshot({ ws, snapshot: s1 })
  const e2 = w.diff('r', s1, s2)
  assert.deepEqual(e2.map(e => [e.kind, e.run]), [['run', 'ship/run-watch']])
  assert.equal(e2[0].rev, s1.get('\0run:ship/run-watch')?.hash, 'the record itself did not change')
  const d = await createRun(ws, base({ name: 'run-watch2' }))
  const s3 = await w.snapshot({ ws, snapshot: s2 })
  assert.deepEqual(w.diff('r', s2, s3).map(e => [e.kind, e.run ?? null]), [['run', `ship/${d.ref.run}`], ['runs', null]])
  assert.equal(w.diff('r', s3, await w.snapshot({ ws, snapshot: s3 })).length, 0, 'an idle tick reports nothing')
})

test('operation parity: every operation through HTTP yields the same record as through the CLI module', async () => {
  const { createHandler } = await import('../server/api.ts')
  const { createServer } = await import('node:http')
  const handler = createHandler({ registryFile: registry, area: root, allowedOrigins: [], allowedHosts: ['127.0.0.1'] })
  const server = createServer((req, res) => void handler(req, res))
  await new Promise<void>(r => server.listen(0, '127.0.0.1', () => r()))
  const url = `http://127.0.0.1:${(server.address() as { port: number }).port}/api/workspaces/r`
  const ops: (OpInput & Record<string, unknown>)[] = [
    { op: 'node.start', node: 'survey' },
    { op: 'node.progress', node: 'survey', text: 'half way' },
    { op: 'question.ask', question: '', node: 'survey', text: 'Scope?', to: 'Test Person' },
    { op: 'question.answer', question: 'q1', text: 'Small', from: 'Test Person' },
    { op: 'question.take-up', question: 'q1' },
    { op: 'artifact.attach', path: 'devdocs/README.md', node: 'survey', title: 'readme' },
    { op: 'node.complete', node: 'survey', outcome: 'ok', artifacts: ['devdocs/README.md'] },
    { op: 'node.start', node: 'build' },
    { op: 'node.wait', node: 'build', reason: 'CI', holder: 'CI service', external: 'build #12' },
    { op: 'node.start', node: 'build' },
    { op: 'node.fail', node: 'build', reason: 'red' },
    { op: 'node.start', node: 'build', reason: 'retry by hand' },
    { op: 'node.cancel', node: 'build', reason: 'dropped' },
    { op: 'node.start', node: 'ask' },
    { op: 'question.ask', question: '', node: 'ask', text: 'Withdrawn later', to: 'Test Person' },
    { op: 'question.withdraw', question: 'q2', reason: 'not needed' },
    { op: 'node.start', node: 'handoff' },
    { op: 'node.delegate', node: 'handoff', child: { workflow: 'sub', run: 'run-x' } },
    { op: 'run.decide', decision: 'rejected', evidence: 'the build was dropped' },
    { op: 'run.cancel', reason: 'parity done' },
  ]
  try {
    const a = await createRun(ws, base({ name: 'run-parity-cli' }))
    const b = await createRun(ws, base({ name: 'run-parity-http' }))
    for (const o of ops) {
      if (o.op === 'node.delegate') await delegate(ws, a.ref, o.node, { via: 'cli', by: 'Omni Agent', name: 'run-parity-cli' })
      else await runOp(ws, a.ref, o, { via: 'cli', by: 'Omni Agent' })
      const body = o.op === 'node.delegate' ? { op: o.op, node: o.node, name: 'run-parity-http', by: 'Omni Agent' } : { ...o, by: 'Omni Agent' }
      const r = await fetch(`${url}/runs/ship/run-parity-http/ops`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
      assert.equal(r.status, 200, `${o.op}: ${await r.clone().text()}`)
    }
    // Same record except route, times, the run's own name and the dirty count
    // of devdocs at creation (the second run sees the first run's files).
    const norm = (rec: RunRecord) => JSON.parse(JSON.stringify(rec)
      .replace(/"\d{4}-\d\d-\d\dT[^"]+Z"/g, '"T"').replace(/"via":"(cli|browser)"/g, '"via":"V"').replace(/run-parity-(cli|http)/g, 'run-P').replace(/"dirty":\d+/g, '"dirty":0'))
    const ra = (await readRun(ws, a.ref)).record!, rb = (await readRun(ws, b.ref)).record!
    assert.deepEqual(norm(rb), norm(ra))
    assert.deepEqual([...new Set(rb.history.slice(1).map(e => e.via))], ['browser'])
    assert.equal((await readRun(ws, { workflow: 'sub', run: 'run-parity-http' })).record?.parent?.run, 'run-parity-http')
  } finally {
    server.closeAllConnections(); server.close()
  }
})
