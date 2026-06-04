#!/usr/bin/env node
/**
 * Standalone installer for lark-skills.
 * Usage: npx github:allday9z/lark-skills
 *    or: node install.js
 */
const { execSync, spawnSync } = require('child_process')
const path = require('path')
const fs   = require('fs')
const os   = require('os')

const SKILL_NAME = 'lark'
const SKILL_DIR  = path.join(os.homedir(), '.claude', 'skills', SKILL_NAME)
const REPO_URL   = 'https://github.com/allday9z/lark-skills'

function run(cmd, opts = {}) {
  return execSync(cmd, { stdio: 'pipe', ...opts }).toString().trim()
}

function log(msg)  { console.log(`  ${msg}`) }
function ok(msg)   { console.log(`  ✅ ${msg}`) }
function warn(msg) { console.log(`  ⚠️  ${msg}`) }
function err(msg)  { console.error(`  ❌ ${msg}`); process.exit(1) }

console.log('\n🔧 Installing lark-skills...\n')

// 1. Ensure ~/.claude/skills/ exists
fs.mkdirSync(path.join(os.homedir(), '.claude', 'skills'), { recursive: true })

// 2. Clone or update
if (fs.existsSync(SKILL_DIR)) {
  log('Skill directory exists — updating...')
  try {
    run('git pull', { cwd: SKILL_DIR })
    ok('Updated to latest')
  } catch {
    warn('git pull failed — using existing version')
  }
} else {
  log('Cloning lark-skills...')
  try {
    run(`git clone --depth 1 ${REPO_URL} "${SKILL_DIR}"`)
    ok('Cloned successfully')
  } catch {
    err(`Failed to clone ${REPO_URL}. Check network/git.`)
  }
}

// 3. Check Python
const py = spawnSync('python3', ['--version'])
if (py.status !== 0) {
  err('python3 not found. Install Python 3.8+.')
}
ok(`Python: ${py.stdout.toString().trim()}`)

// 4. Show next steps
console.log(`
✅ lark-skills installed at: ${SKILL_DIR}

Next steps:
  1. Run setup:
     python3 ${SKILL_DIR}/scripts/setup.py

  2. Verify token:
     python3 ${SKILL_DIR}/scripts/token_manager.py

  3. In Claude Code, use /lark skill or reference:
     ~/.claude/skills/lark/SKILL.md

Docs: ${REPO_URL}
`)
