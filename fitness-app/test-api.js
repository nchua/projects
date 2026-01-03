#!/usr/bin/env node

/**
 * Test API endpoints
 */

const http = require('http');

function testEndpoint(path, method = 'GET', body = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'localhost',
      port: 8000,
      path: path,
      method: method,
      headers: {
        'Content-Type': 'application/json'
      }
    };

    const req = http.request(options, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const parsed = JSON.parse(data);
          resolve({ status: res.statusCode, data: parsed });
        } catch (e) {
          resolve({ status: res.statusCode, data: data });
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    if (body) {
      req.write(JSON.stringify(body));
    }

    req.end();
  });
}

async function main() {
  console.log('Testing Fitness Tracker API\n');
  console.log('='.repeat(50));

  // Test health endpoint
  try {
    console.log('\n✓ Testing GET /health');
    const health = await testEndpoint('/health');
    console.log(`  Status: ${health.status}`);
    console.log(`  Response:`, JSON.stringify(health.data, null, 2));

    if (health.status === 200 && health.data.status === 'ok') {
      console.log('  ✅ Health check passed');
    } else {
      console.log('  ❌ Health check failed');
    }
  } catch (error) {
    console.log('  ❌ Health check failed:', error.message);
  }

  // Test root endpoint
  try {
    console.log('\n✓ Testing GET /');
    const root = await testEndpoint('/');
    console.log(`  Status: ${root.status}`);
    console.log(`  Response:`, JSON.stringify(root.data, null, 2));

    if (root.status === 200) {
      console.log('  ✅ Root endpoint passed');
    } else {
      console.log('  ❌ Root endpoint failed');
    }
  } catch (error) {
    console.log('  ❌ Root endpoint failed:', error.message);
  }

  console.log('\n' + '='.repeat(50));
  console.log('\nAPI tests complete!');
}

main().catch(console.error);
