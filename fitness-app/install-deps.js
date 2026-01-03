#!/usr/bin/env node

/**
 * Install Python dependencies
 */

const { spawnSync } = require('child_process');
const path = require('path');

const backendDir = path.join(__dirname, 'backend');
const pipPath = path.join(backendDir, 'venv', 'bin', 'pip');
const requirementsPath = path.join(backendDir, 'requirements-dev.txt');

console.log('📦 Installing Python dependencies...\n');

const result = spawnSync(pipPath, [
  'install',
  '-r',
  requirementsPath
], {
  stdio: 'inherit',
  cwd: backendDir
});

if (result.error) {
  console.error('Failed to install dependencies:', result.error);
  process.exit(1);
}

if (result.status !== 0) {
  console.error(`Installation failed with exit code ${result.status}`);
  process.exit(result.status);
}

console.log('\n✅ Dependencies installed successfully!');
