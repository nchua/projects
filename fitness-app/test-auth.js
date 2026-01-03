#!/usr/bin/env node

/**
 * Test authentication endpoints
 */

const http = require('http');

const BASE_URL = 'http://localhost:8000';

// Helper function to make HTTP requests
function makeRequest(method, path, data = null) {
    return new Promise((resolve, reject) => {
        const url = new URL(path, BASE_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname + url.search,
            method: method,
            headers: {
                'Content-Type': 'application/json',
            }
        };

        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', (chunk) => body += chunk);
            res.on('end', () => {
                try {
                    const response = JSON.parse(body);
                    resolve({ status: res.statusCode, data: response });
                } catch (e) {
                    resolve({ status: res.statusCode, data: body });
                }
            });
        });

        req.on('error', reject);

        if (data) {
            req.write(JSON.stringify(data));
        }
        req.end();
    });
}

async function testAuth() {
    console.log('Testing Authentication Endpoints\n');
    console.log('='.repeat(50));

    // Generate unique email for testing
    const timestamp = Date.now();
    const testEmail = `test${timestamp}@example.com`;
    const testPassword = 'TestPass123';

    let accessToken = '';
    let refreshToken = '';

    // Test 1: Register new user
    console.log('\n✓ Testing POST /auth/register');
    try {
        const registerResult = await makeRequest('POST', '/auth/register', {
            email: testEmail,
            password: testPassword
        });
        console.log(`  Status: ${registerResult.status}`);
        console.log(`  Response:`, JSON.stringify(registerResult.data, null, 2));

        if (registerResult.status === 201) {
            console.log('  ✅ Registration successful');
        } else {
            console.log('  ❌ Registration failed');
            return;
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
        return;
    }

    // Test 2: Try to register duplicate email
    console.log('\n✓ Testing POST /auth/register (duplicate email)');
    try {
        const duplicateResult = await makeRequest('POST', '/auth/register', {
            email: testEmail,
            password: testPassword
        });
        console.log(`  Status: ${duplicateResult.status}`);
        console.log(`  Response:`, JSON.stringify(duplicateResult.data, null, 2));

        if (duplicateResult.status === 400) {
            console.log('  ✅ Duplicate email properly rejected');
        } else {
            console.log('  ❌ Duplicate email should return 400');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 3: Login with valid credentials
    console.log('\n✓ Testing POST /auth/login (valid credentials)');
    try {
        const loginResult = await makeRequest('POST', '/auth/login', {
            email: testEmail,
            password: testPassword
        });
        console.log(`  Status: ${loginResult.status}`);
        console.log(`  Response:`, JSON.stringify(loginResult.data, null, 2));

        if (loginResult.status === 200 && loginResult.data.access_token) {
            console.log('  ✅ Login successful, tokens received');
            accessToken = loginResult.data.access_token;
            refreshToken = loginResult.data.refresh_token;
        } else {
            console.log('  ❌ Login failed');
            return;
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
        return;
    }

    // Test 4: Login with invalid credentials
    console.log('\n✓ Testing POST /auth/login (invalid password)');
    try {
        const invalidLoginResult = await makeRequest('POST', '/auth/login', {
            email: testEmail,
            password: 'WrongPassword123'
        });
        console.log(`  Status: ${invalidLoginResult.status}`);
        console.log(`  Response:`, JSON.stringify(invalidLoginResult.data, null, 2));

        if (invalidLoginResult.status === 401) {
            console.log('  ✅ Invalid credentials properly rejected');
        } else {
            console.log('  ❌ Invalid credentials should return 401');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 5: Refresh token
    console.log('\n✓ Testing POST /auth/refresh');
    try {
        const refreshResult = await makeRequest('POST', '/auth/refresh', {
            refresh_token: refreshToken
        });
        console.log(`  Status: ${refreshResult.status}`);
        console.log(`  Response:`, JSON.stringify(refreshResult.data, null, 2));

        if (refreshResult.status === 200 && refreshResult.data.access_token) {
            console.log('  ✅ Token refresh successful');
        } else {
            console.log('  ❌ Token refresh failed');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 6: Refresh with invalid token
    console.log('\n✓ Testing POST /auth/refresh (invalid token)');
    try {
        const invalidRefreshResult = await makeRequest('POST', '/auth/refresh', {
            refresh_token: 'invalid_token_12345'
        });
        console.log(`  Status: ${invalidRefreshResult.status}`);
        console.log(`  Response:`, JSON.stringify(invalidRefreshResult.data, null, 2));

        if (invalidRefreshResult.status === 401) {
            console.log('  ✅ Invalid refresh token properly rejected');
        } else {
            console.log('  ❌ Invalid refresh token should return 401');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 7: Weak password validation
    console.log('\n✓ Testing POST /auth/register (weak password)');
    try {
        const weakPasswordResult = await makeRequest('POST', '/auth/register', {
            email: `weak${timestamp}@example.com`,
            password: 'weak'
        });
        console.log(`  Status: ${weakPasswordResult.status}`);
        console.log(`  Response:`, JSON.stringify(weakPasswordResult.data, null, 2));

        if (weakPasswordResult.status === 422) {
            console.log('  ✅ Weak password properly rejected');
        } else {
            console.log('  ⚠️  Weak password validation (status:', weakPasswordResult.status, ')');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    console.log('\n' + '='.repeat(50));
    console.log('\nAuth endpoint tests complete!\n');
}

// Run tests
testAuth().catch(console.error);
