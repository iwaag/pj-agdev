// Starts the local editor service.
//
//   node server/main.ts [--registry <file>] [--area <dir>] [--port 8095]
//     [--poll-ms 1000] [--git-poll-ms 3000] [--serve-dist]
//
// The registry defaults to pj-agdev/.local/workflow-editor/registry.json (the
// p1 fixture); `wfe serve` starts it for an authoring area's registry instead.
// The area (default: the registry's directory) is where browser-created
// projects go.
//
// It binds to 127.0.0.1 only. Browser writes are accepted from the Vite dev
// origin and from its own origin (when serving the built UI).
import { createServer } from 'node:http'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createHandler } from './api.ts'
import { Watcher } from './watch.ts'

const here = dirname(fileURLToPath(import.meta.url))
const experiment = resolve(here, '..')
const args = process.argv.slice(2)
const option = (name: string, fallback: string) => { const i = args.indexOf(name); return i >= 0 ? args[i + 1] : process.env[`WFE_${name.slice(2).toUpperCase()}`] ?? fallback }

export const DEFAULT_PORT = 8095
export const DEV_PORT = 5175
const port = Number(option('--port', String(DEFAULT_PORT)))
const registryFile = resolve(option('--registry', join(experiment, '..', '..', '.local', 'workflow-editor', 'registry.json')))
const area = resolve(option('--area', dirname(registryFile)))
const serveDist = args.includes('--serve-dist')
const pollMs = Number(option('--poll-ms', '1000'))
const gitPollMs = Number(option('--git-poll-ms', '3000'))

const origins = [`http://127.0.0.1:${port}`, `http://localhost:${port}`, `http://127.0.0.1:${DEV_PORT}`, `http://localhost:${DEV_PORT}`]
const handler = createHandler({
  registryFile,
  area,
  allowedOrigins: origins,
  allowedHosts: ['127.0.0.1', 'localhost'],
  distDir: serveDist ? join(experiment, 'dist') : undefined,
  watcher: new Watcher(pollMs, { gitIntervalMs: gitPollMs, registryFile }),
})

const server = createServer((req, res) => void handler(req, res))
server.on('error', (e: NodeJS.ErrnoException) => {
  if (e.code === 'EADDRINUSE') console.error(`Port ${port} is already in use on 127.0.0.1 — another editor service is probably running. Stop it, or pass --port.`)
  else console.error(e)
  process.exit(1)
})
server.listen(port, '127.0.0.1', () => {
  console.log(`workflow editor service on http://127.0.0.1:${port}${serveDist ? ' (serving dist/)' : ''}`)
  console.log(`registry: ${registryFile}`)
  console.log(`authoring area: ${area}`)
})
