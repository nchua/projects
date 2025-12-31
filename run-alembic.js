#!/usr/bin/env node

/**
 * Run Alembic migration commands
 */

const { spawnSync } = require('child_process');
const path = require('path');

const backendDir = path.join(__dirname, 'backend');
const alembicPath = path.join(backendDir, 'venv', 'bin', 'alembic');

// Get command from arguments
const command = process.argv.slice(2);

if (command.length === 0) {
  console.error('Usage: node run-alembic.js <alembic command>');
  console.error('Example: node run-alembic.js revision --autogenerate -m "Initial migration"');
  process.exit(1);
}

console.log(`Running: alembic ${command.join(' ')}\n`);

const result = spawnSync(alembicPath, command, {
  stdio: 'inherit',
  cwd: backendDir
});

process.exit(result.status);
