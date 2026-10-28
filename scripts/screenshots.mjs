// Renders the static dashboard on the fixture jobs and saves a light and a dark screenshot for the READMEs.
// Usage: node scripts/screenshots.mjs   (needs python3 and the playwright package, resolved from NODE_PATH or globally)
import { execSync, spawn } from 'node:child_process'
import { cpSync, mkdtempSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const out = join(root, 'docs', 'images')
const PORT = 8765

function loadPlaywright() {
  const require = createRequire(import.meta.url)
  try {
    return require('playwright')
  } catch {
    return require(join(execSync('npm root -g').toString().trim(), 'playwright'))
  }
}

const site = mkdtempSync(join(tmpdir(), 'clay-shots-'))
cpSync(join(root, 'tests', 'fixtures', 'jobs'), site, { recursive: true })
cpSync(join(root, 'plugins', 'clay', 'factory', 'dashboard.html'), join(site, 'dashboard.html'))

// The dashboard lists folders from the server's HTML index, so it needs a server that writes one.
const server = spawn('python3', ['-m', 'http.server', String(PORT), '--bind', '127.0.0.1'], { cwd: site, stdio: 'ignore' })
const { chromium } = loadPlaywright()
const browser = await chromium.launch()
try {
  for (const scheme of ['light', 'dark']) {
    const page = await browser.newPage({ viewport: { width: 1000, height: 300 }, colorScheme: scheme, deviceScaleFactor: 2 })
    for (let tries = 0; ; tries++) {
      try {
        await page.goto(`http://127.0.0.1:${PORT}/dashboard.html`)
        break
      } catch (err) {
        if (tries > 20) throw err
        await new Promise(r => setTimeout(r, 200))
      }
    }
    await page.waitForSelector('.card')
    await page.waitForTimeout(500)
    await page.screenshot({ path: join(out, `dashboard-${scheme}.png`), fullPage: true })
    await page.close()
  }
} finally {
  await browser.close()
  server.kill()
  rmSync(site, { recursive: true, force: true })
}
console.log(`saved to ${out}`)
