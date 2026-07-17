import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = process.cwd()
const srcDir = join(root, 'src')
const failures = []

function walk(dir, predicate, acc = []) {
  for (const entry of readdirSync(dir)) {
    const fullPath = join(dir, entry)
    const stat = statSync(fullPath)
    if (stat.isDirectory()) {
      walk(fullPath, predicate, acc)
    } else if (predicate(fullPath)) {
      acc.push(fullPath)
    }
  }
  return acc
}

const jsInSrc = walk(srcDir, file => file.endsWith('.js'))
if (jsInSrc.length) {
  failures.push(
    `src contains JavaScript shadow files:\n${jsInSrc.map(file => `  - ${relative(root, file)}`).join('\n')}`,
  )
}

const mainTs = readFileSync(join(srcDir, 'main.ts'), 'utf8')
if (!mainTs.includes("from './router/index.ts'")) {
  failures.push("src/main.ts must import router from './router/index.ts'")
}

const legacyRouter = join(srcDir, 'router', 'index.js')
if (existsSync(legacyRouter)) {
  failures.push('src/router/index.js must stay out of src; move legacy router code to legacy-shadow-src')
}

const viteConfig = readFileSync(join(root, 'vite.config.ts'), 'utf8')
if (!viteConfig.includes("extensions: ['.ts', '.tsx', '.vue'")) {
  failures.push('vite.config.ts must resolve .ts/.tsx/.vue before .js')
}

if (failures.length) {
  console.error(failures.join('\n\n'))
  process.exit(1)
}

console.log('frontend entry verification passed')
