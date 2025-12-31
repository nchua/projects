#!/usr/bin/env node

/**
 * Test user profile endpoints
 */

const http = require('http');

const BASE_URL = 'http://localhost:8000';

// Helper function to make HTTP requests
function makeRequest(method, path, data = null, token = null) {
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

        // Add authorization header if token provided
        if (token) {
            options.headers['Authorization'] = `Bearer ${token}`;
        }

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

async function testProfile() {
    console.log('Testing User Profile Endpoints\n');
    console.log('='.repeat(50));

    // Generate unique email for testing
    const timestamp = Date.now();
    const testEmail = `profile${timestamp}@example.com`;
    const testPassword = 'TestPass123';

    let accessToken = '';

    // Test 1: Register new user
    console.log('\n✓ Setting up test user');
    try {
        const registerResult = await makeRequest('POST', '/auth/register', {
            email: testEmail,
            password: testPassword
        });

        if (registerResult.status !== 201) {
            console.log('  ❌ Failed to register test user');
            return;
        }

        // Login to get token
        const loginResult = await makeRequest('POST', '/auth/login', {
            email: testEmail,
            password: testPassword
        });

        if (loginResult.status !== 200) {
            console.log('  ❌ Failed to login');
            return;
        }

        accessToken = loginResult.data.access_token;
        console.log('  ✅ Test user created and authenticated');
    } catch (error) {
        console.log('  ❌ Error:', error.message);
        return;
    }

    // Test 2: Get default profile
    console.log('\n✓ Testing GET /profile/ (default profile)');
    try {
        const profileResult = await makeRequest('GET', '/profile/', null, accessToken);
        console.log(`  Status: ${profileResult.status}`);
        console.log(`  Response:`, JSON.stringify(profileResult.data, null, 2));

        if (profileResult.status === 200) {
            console.log('  ✅ Default profile retrieved successfully');
        } else {
            console.log('  ❌ Failed to retrieve profile');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 3: Update profile with all fields
    console.log('\n✓ Testing PUT /profile/ (update all fields)');
    try {
        const updateResult = await makeRequest('PUT', '/profile/', {
            age: 30,
            sex: 'M',
            bodyweight_lb: 180.5,
            training_experience: 'intermediate',
            preferred_unit: 'lb',
            e1rm_formula: 'epley'
        }, accessToken);
        console.log(`  Status: ${updateResult.status}`);
        console.log(`  Response:`, JSON.stringify(updateResult.data, null, 2));

        if (updateResult.status === 200) {
            console.log('  ✅ Profile updated successfully');
        } else {
            console.log('  ❌ Failed to update profile');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 4: Get updated profile
    console.log('\n✓ Testing GET /profile (after update)');
    try {
        const profileResult = await makeRequest('GET', '/profile', null, accessToken);
        console.log(`  Status: ${profileResult.status}`);
        console.log(`  Response:`, JSON.stringify(profileResult.data, null, 2));

        if (profileResult.status === 200 && profileResult.data.age === 30) {
            console.log('  ✅ Updated profile retrieved with correct data');
        } else {
            console.log('  ❌ Profile data mismatch');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 5: Update only specific fields
    console.log('\n✓ Testing PUT /profile (partial update)');
    try {
        const updateResult = await makeRequest('PUT', '/profile', {
            age: 31,
            bodyweight_lb: 185.0
        }, accessToken);
        console.log(`  Status: ${updateResult.status}`);
        console.log(`  Response:`, JSON.stringify(updateResult.data, null, 2));

        if (updateResult.status === 200 && updateResult.data.age === 31 && updateResult.data.bodyweight_lb === 185.0) {
            console.log('  ✅ Partial update successful');
        } else {
            console.log('  ❌ Partial update failed');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 6: Try to access profile without authentication
    console.log('\n✓ Testing GET /profile (no auth token)');
    try {
        const profileResult = await makeRequest('GET', '/profile', null, null);
        console.log(`  Status: ${profileResult.status}`);
        console.log(`  Response:`, JSON.stringify(profileResult.data, null, 2));

        if (profileResult.status === 403 || profileResult.status === 401) {
            console.log('  ✅ Unauthorized access properly rejected');
        } else {
            console.log('  ❌ Should return 401/403 without auth');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 7: Try to access with invalid token
    console.log('\n✓ Testing GET /profile (invalid token)');
    try {
        const profileResult = await makeRequest('GET', '/profile', null, 'invalid_token_12345');
        console.log(`  Status: ${profileResult.status}`);
        console.log(`  Response:`, JSON.stringify(profileResult.data, null, 2));

        if (profileResult.status === 401) {
            console.log('  ✅ Invalid token properly rejected');
        } else {
            console.log('  ❌ Should return 401 with invalid token');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    console.log('\n' + '='.repeat(50));
    console.log('\nProfile endpoint tests complete!\n');
}

// Run tests
testProfile().catch(console.error);
