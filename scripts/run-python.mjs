import { existsSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const scriptDirectory = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(scriptDirectory, '..')
const configuredPython = process.env.STOCKLLM_PYTHON
const localPython = process.platform === 'win32'
  ? resolve(projectRoot, '.venv', 'Scripts', 'python.exe')
  : resolve(projectRoot, '.venv', 'bin', 'python')
const python = configuredPython || (existsSync(localPython) ? localPython : process.platform === 'win32' ? 'python' : 'python3')
const result = spawnSync(python, process.argv.slice(2), { cwd: process.cwd(), stdio: 'inherit' })

if (result.error) throw result.error
process.exit(result.status ?? 1)
