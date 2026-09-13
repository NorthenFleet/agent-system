import { mkdir, readFile, writeFile } from 'node:fs/promises'
import { resolve } from 'node:path'

const originIndex = process.argv.indexOf('--origin')
const origin = (originIndex >= 0 ? process.argv[originIndex + 1] : process.env.WORD_ADDIN_ORIGIN || '').replace(/\/+$/, '')
if (!origin.startsWith('https://')) {
  throw new Error('WORD_ADDIN_ORIGIN must be an https:// origin')
}

const root = resolve(import.meta.dirname, '..')
const template = await readFile(resolve(root, 'word-addin/manifest.template.xml'), 'utf8')
const manifest = template.replaceAll('__WORD_ADDIN_ORIGIN__', origin)
const outputDir = resolve(root, 'dist/word-addin')
const artifactDir = resolve(root, 'artifacts/word-addin')
await mkdir(outputDir, { recursive: true })
await mkdir(artifactDir, { recursive: true })
await writeFile(resolve(outputDir, 'manifest.xml'), manifest)
await writeFile(resolve(artifactDir, '3021-word-addin-manifest.xml'), manifest)
console.log(`Word Add-in manifest: ${resolve(artifactDir, '3021-word-addin-manifest.xml')}`)
