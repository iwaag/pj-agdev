// Observes definition files by bounded polling and pushes changes to browsers
// over Server-Sent Events. Polling is simple, works the same on every
// platform and editor (including atomic-rename saves), and costs a few small
// reads per second while a browser is connected. It only runs then.
import type { IncomingMessage, ServerResponse } from 'node:http'
import { readdir } from 'node:fs/promises'
import type { ChangeEvent } from '../shared/api.ts'
import { inside, readTextOrNull, textHash } from './files.ts'
import { WORKFLOW_FILE, WORKFLOWS_DIR, type Workspace } from './workspace.ts'

const MAX_FILES = 200

interface Entry { ws: Workspace; clients: Set<ServerResponse>; snapshot: Map<string, string | null> | null; timer?: NodeJS.Timeout; busy: boolean }

export class Watcher {
  readonly intervalMs: number
  private entries = new Map<string, Entry>()
  private ownWrites = new Map<string, string>() // `${ws}\0${path}` -> rev

  constructor(intervalMs = 1000) { this.intervalMs = intervalMs }

  noteOwnWrite(ws: Workspace, path: string, rev: string) {
    this.ownWrites.set(`${ws.reg.id}\0${path}`, rev)
  }

  async snapshot(ws: Workspace): Promise<Map<string, string | null>> {
    const snap = new Map<string, string | null>()
    for (const rel of ['project.yaml', '.gitmodules']) {
      const text = await readTextOrNull(await inside(ws.root, rel)).catch(() => null)
      snap.set(rel, text === null ? null : textHash(text))
    }
    const dir = await inside(ws.root, WORKFLOWS_DIR)
    const files = (await readdir(dir).catch(() => [] as string[])).filter(f => WORKFLOW_FILE.test(f)).sort().slice(0, MAX_FILES)
    for (const f of files) {
      const text = await readTextOrNull(`${dir}/${f}`).catch(() => null)
      snap.set(`${WORKFLOWS_DIR}/${f}`, text === null ? null : textHash(text))
    }
    return snap
  }

  diff(ws: Workspace, before: Map<string, string | null>, after: Map<string, string | null>): (ChangeEvent & { byEditor: boolean })[] {
    const events: (ChangeEvent & { byEditor: boolean })[] = []
    const keys = new Set([...before.keys(), ...after.keys()])
    let listChanged = false
    for (const key of keys) {
      const a = before.get(key) ?? null, b = after.get(key) ?? null
      if (a === b) continue
      const byEditor = b !== null && this.ownWrites.get(`${ws.reg.id}\0${key}`) === b
      if (key === 'project.yaml') events.push({ type: 'changed', workspace: ws.reg.id, kind: 'project', rev: b, byEditor })
      else if (key === '.gitmodules') events.push({ type: 'changed', workspace: ws.reg.id, kind: 'repositories', rev: b, byEditor })
      else {
        if (!before.has(key) || !after.has(key)) listChanged = true
        events.push({ type: 'changed', workspace: ws.reg.id, kind: 'workflow', file: key.slice(WORKFLOWS_DIR.length + 1), rev: b, byEditor })
      }
    }
    if (listChanged) events.push({ type: 'changed', workspace: ws.reg.id, kind: 'workflows', rev: null, byEditor: false })
    return events
  }

  private async tick(entry: Entry) {
    if (entry.busy) return
    entry.busy = true
    try {
      const next = await this.snapshot(entry.ws)
      if (entry.snapshot) {
        for (const event of this.diff(entry.ws, entry.snapshot, next)) {
          const line = `event: change\ndata: ${JSON.stringify(event)}\n\n`
          for (const c of entry.clients) c.write(line)
        }
      }
      entry.snapshot = next
    } catch (e) {
      for (const c of entry.clients) c.write(`event: watch-error\ndata: ${JSON.stringify({ error: (e as Error).message })}\n\n`)
    } finally {
      entry.busy = false
    }
  }

  stream(ws: Workspace, req: IncomingMessage, res: ServerResponse) {
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-store', connection: 'keep-alive' })
    res.write(`event: hello\ndata: ${JSON.stringify({ workspace: ws.reg.id, intervalMs: this.intervalMs })}\n\n`)
    let entry = this.entries.get(ws.reg.id)
    if (!entry) {
      entry = { ws, clients: new Set(), snapshot: null, busy: false }
      this.entries.set(ws.reg.id, entry)
      void this.tick(entry)
      entry.timer = setInterval(() => void this.tick(entry!), this.intervalMs)
    }
    entry.clients.add(res)
    const heartbeat = setInterval(() => res.write(': keep-alive\n\n'), 15_000)
    req.on('close', () => {
      clearInterval(heartbeat)
      entry!.clients.delete(res)
      if (entry!.clients.size === 0) {
        clearInterval(entry!.timer)
        this.entries.delete(ws.reg.id)
      }
    })
  }
}
