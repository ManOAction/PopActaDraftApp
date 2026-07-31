/**
 * Design-loop driver: boot the app, capture it at real viewport sizes, and report
 * any console or page error it produced.
 *
 * This exists so a design-review agent can run one command, look at the PNGs, and
 * critique the result — rather than reasoning about JSX and guessing how it renders.
 *
 *   npm run screenshot                 # default route, both viewports
 *   npm run screenshot -- /board       # a specific route
 *   npm run screenshot -- / --keep     # leave the dev server running
 *
 * Mobile comes first because the draft happens on a phone.
 */

import { spawn, spawnSync, type ChildProcess } from 'node:child_process'
import { mkdir, rm } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { chromium, devices } from '@playwright/test'

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const OUT_DIR = resolve(WEB_ROOT, 'screenshots')
const PORT = 5199 // Deliberately not 5173, so this never fights a dev server you already have open.
const BASE_URL = `http://127.0.0.1:${PORT}`
const SERVER_TIMEOUT_MS = 60_000

const VIEWPORTS = [
  { name: 'mobile', options: devices['iPhone 15'] },
  { name: 'desktop', options: { viewport: { width: 1440, height: 900 } } },
] as const

function parseArgs(argv: string[]): { route: string; keep: boolean } {
  const args = argv.slice(2)
  const keep = args.includes('--keep')
  const route = args.find((a) => !a.startsWith('--')) ?? '/'
  return { route: route.startsWith('/') ? route : `/${route}`, keep }
}

async function waitForServer(url: string, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(2000) })
      if (res.ok) return
    } catch {
      // Server not up yet. Retrying is the whole point of this loop; swallowing
      // here is intentional and bounded by `deadline`.
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`Dev server did not answer on ${url} within ${timeoutMs}ms`)
}

function startDevServer(): ChildProcess {
  // Run Vite's JS entrypoint under the current Node binary rather than shelling out
  // to the `npx`/`vite` .cmd shims. Spawning a .cmd on Windows needs `shell: true`,
  // which Node flags as a security deprecation (DEP0190) and which mangles quoting.
  const viteBin = resolve(WEB_ROOT, 'node_modules/vite/bin/vite.js')
  const child = spawn(process.execPath, [viteBin, '--port', String(PORT), '--strictPort'], {
    cwd: WEB_ROOT,
    stdio: 'ignore',
    // POSIX: own process group, so we can signal the whole tree below.
    detached: process.platform !== 'win32',
  })
  child.on('error', (err) => {
    throw new Error(`Failed to start dev server: ${err.message}`)
  })
  return child
}

/**
 * Kill the dev server *and its descendants*.
 *
 * `child.kill()` alone signals only the process we spawned. Vite's workers survive it,
 * keep the port bound, and — on Windows — hold native `.node` binaries open, which makes
 * a later `npm ci` fail with `EPERM: unlink lightningcss.win32-x64-msvc.node`. Leaking a
 * server per run is not acceptable for something meant to run on every design iteration.
 */
function killTree(child: ChildProcess): void {
  if (child.pid === undefined || child.exitCode !== null || child.signalCode !== null) return

  if (process.platform === 'win32') {
    spawnSync('taskkill', ['/pid', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
  } else {
    try {
      process.kill(-child.pid, 'SIGTERM') // negative pid == the whole process group
    } catch {
      child.kill('SIGKILL')
    }
  }
}

async function main(): Promise<void> {
  const { route, keep } = parseArgs(process.argv)

  await rm(OUT_DIR, { recursive: true, force: true })
  await mkdir(OUT_DIR, { recursive: true })

  const server = startDevServer()
  // Ctrl-C and hard exits bypass `finally`; without this the server outlives the script.
  const onSignal = (): void => {
    killTree(server)
    process.exit(130)
  }
  process.once('SIGINT', onSignal)
  process.once('SIGTERM', onSignal)

  const browser = await chromium.launch()
  const problems: string[] = []

  try {
    await waitForServer(BASE_URL, SERVER_TIMEOUT_MS)

    for (const { name, options } of VIEWPORTS) {
      const context = await browser.newContext(options)
      const page = await context.newPage()

      page.on('console', (msg) => {
        if (msg.type() === 'error') problems.push(`[${name}] console: ${msg.text()}`)
      })
      page.on('pageerror', (err) => problems.push(`[${name}] pageerror: ${err.message}`))

      await page.goto(`${BASE_URL}${route}`, { waitUntil: 'networkidle' })

      const file = resolve(OUT_DIR, `${name}.png`)
      await page.screenshot({ path: file, fullPage: true })
      console.log(`${name.padEnd(8)} -> ${file}`)

      await context.close()
    }
  } finally {
    await browser.close()
    if (keep) {
      process.off('SIGINT', onSignal)
      process.off('SIGTERM', onSignal)
    } else {
      killTree(server)
    }
  }

  if (problems.length > 0) {
    // A screenshot of a broken page still looks like a screenshot. Make the
    // failure impossible to scroll past.
    console.error(`\n${problems.length} browser error(s):`)
    for (const p of problems) console.error(`  ${p}`)
    process.exitCode = 1
    return
  }

  console.log(`\nClean render of ${route} — no console or page errors.`)
  if (keep) console.log(`Dev server left running at ${BASE_URL}`)
}

await main()
