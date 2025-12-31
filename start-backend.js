#!/usr/bin/env node

/**
 * Backend server starter script
 * Starts the FastAPI backend using uvicorn
 */

const { spawn } = require('child_process');
const path = require('path');

const backendDir = path.join(__dirname, 'backend');
const pythonPath = path.join(backendDir, 'venv', 'bin', 'python');
const uvicornPath = path.join(backendDir, 'venv', 'bin', 'uvicorn');

console.log('🏋️  Starting Fitness Tracker API...\n');

// Start uvicorn server (run from backend directory so module imports work)
const server = spawn(uvicornPath, [
  'main:app',
  '--reload',
  '--host', '0.0.0.0',
  '--port', '8000'
], {
  stdio: 'inherit',
  cwd: backendDir
});

server.on('error', (err) => {
  console.error('Failed to start server:', err);
  process.exit(1);
});

server.on('close', (code) => {
  console.log(`\nServer process exited with code ${code}`);
  process.exit(code);
});

// Handle graceful shutdown
process.on('SIGINT', () => {
  console.log('\n\nShutting down server...');
  server.kill('SIGINT');
});

process.on('SIGTERM', () => {
  server.kill('SIGTERM');
});
