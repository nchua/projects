#!/usr/bin/env node

/**
 * Run Python seed scripts
 */

const { spawnSync } = require('child_process');
const path = require('path');

const backendDir = path.join(__dirname, 'backend');
const pythonPath = path.join(backendDir, 'venv', 'bin', 'python');
const scriptPath = path.join(backendDir, 'seed_exercises.py');

console.log('Running exercise seed script...\n');

const result = spawnSync(pythonPath, [scriptPath], {
  stdio: 'inherit',
  cwd: backendDir
});

if (result.error) {
  console.error('Failed to run seed script:', result.error);
  process.exit(1);
}

process.exit(result.status);
