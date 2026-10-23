/* Build wrapper: static pre-checks, then `aiot build`, then verify the rpk.
 *
 * Why not call `aiot build` directly: aiot wipes dist/ on every run and, on
 * Windows, its cleanup of the temp project copy fails with EPERM even though
 * the rpk was produced. This wrapper clears dist/, runs the build, tolerates
 * that EPERM when the rpk exists, and prints a short content report.
 */
const { execSync } = require('child_process')
const fs = require('fs')
const path = require('path')

const root = path.resolve(__dirname, '..')
const release = process.argv.indexOf('release') >= 0
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'src/manifest.json'), 'utf8'))
const expect = path.join(root, 'dist',
  `${manifest.package}.${release ? 'release' : 'debug'}.${manifest.versionName}.rpk`)

function fail(msg) {
  console.error('[build] ' + msg)
  process.exit(1)
}

// ---------------------------------------------------------------- pre-checks
const pages = fs.readdirSync(path.join(root, 'src/pages'))
for (const dir of pages) {
  const file = path.join(root, 'src/pages', dir, dir + '.ux')
  if (!fs.existsSync(file)) continue
  const src = fs.readFileSync(file, 'utf8')
  const script = src.slice(src.indexOf('<script>'))
  if (/^\s*data\s*:/m.test(script)) {
    fail(`${dir}.ux 同时出现 data 与 protected（Vela 会直接崩）`)
  }
  if (/opacity\s*:/.test(src)) {
    console.warn(`[build] 警告：${dir}.ux 使用了 opacity，真机上可能渲染出横条纹`)
  }
}

const aboutSrc = fs.readFileSync(path.join(root, 'src/pages/about/about.ux'), 'utf8')
const shown = (aboutSrc.match(/const APP_VERSION = '([^']+)'/) || [])[1]
if (shown !== manifest.versionName) {
  fail(`about.ux 里的版本号 ${shown} 与 manifest 的 ${manifest.versionName} 不一致`)
}

const indexFile = path.join(root, 'src/common/story/index.txt')

if (!fs.existsSync(indexFile)) fail('缺少 src/common/story/index.txt，先跑 python tools/build_story.py')
const index = JSON.parse(fs.readFileSync(indexFile, 'utf8'))
let nodes = 0
for (const c of index.chunks) {
  const f = path.join(root, 'src/common/story/' + c.file.replace('/common/story/', ''))
  if (!fs.existsSync(f)) fail('缺少分块 ' + f)
  nodes += fs.readFileSync(f, 'utf8').split('\n').filter(Boolean).length
}
if (nodes !== index.total) fail(`分块节点数 ${nodes} 与 index.total ${index.total} 不一致`)
console.log(`[build] 剧本 ${index.chapters.length} 章 / ${index.total} 指令 / ${index.chunks.length} 块`)

// ---------------------------------------------------------------- build
fs.rmSync(path.join(root, 'dist'), { recursive: true, force: true })
// aiot 会在上一级建 .temp_<name>（内含 node_modules 联接），Windows 上它自己删不掉；
// 每次构建前先手动清掉，否则第二次构建会卡在 EPERM。
const tmpDir = path.join(path.dirname(root), '.temp_' + path.basename(root))
try { execSync('rmdir /s /q "' + tmpDir + '"', { stdio: 'ignore' }) } catch (e) {}
// 优先用 AIOT 环境变量；否则用本机参考工程里现成的 aiot；都没有就走 npx。
let aiot = process.env.AIOT
if (!aiot) {
  const local = 'D:\\夏末白夜\\手环版\\node_modules\\.bin\\aiot.cmd'
  aiot = fs.existsSync(local) ? local : 'npx aiot'
}
const cmd = aiot.indexOf('npx ') === 0
  ? aiot + ' ' + (release ? 'release' : 'build')
  : '"' + aiot + '" ' + (release ? 'release' : 'build')
try {
  execSync(cmd, { cwd: root, stdio: 'inherit' })
} catch (e) {
  if (!fs.existsSync(expect)) fail('aiot 构建失败：' + e.message)
  console.warn('[build] aiot 退出码非 0（Windows 临时目录清理的已知问题），但产物已生成')
}

if (!fs.existsSync(expect)) fail('没有找到产物 ' + expect)
try { execSync('rmdir /s /q "' + tmpDir + '"', { stdio: 'ignore' }) } catch (e) {}
const size = fs.statSync(expect).size
console.log(`[build] OK ${path.basename(expect)} ${(size / 1048576).toFixed(2)} MB`)
