#!/usr/bin/env node

/**
 * Test exercise endpoints
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

async function testExercises() {
    console.log('Testing Exercise Endpoints\n');
    console.log('='.repeat(50));

    // Generate unique email for testing
    const timestamp = Date.now();
    const testEmail = `exercises${timestamp}@example.com`;
    const testPassword = 'TestPass123';

    let accessToken = '';
    let customExerciseId = '';

    // Setup: Create test user
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

    // Test 1: Get all exercises
    console.log('\n✓ Testing GET /exercises (fetch all)');
    try {
        const result = await makeRequest('GET', '/exercises', null, accessToken);
        console.log(`  Status: ${result.status}`);
        console.log(`  Response: ${result.data.length} exercises returned`);

        if (result.status === 200 && result.data.length > 0) {
            console.log(`  Sample exercises: ${result.data.slice(0, 3).map(ex => ex.name).join(', ')}`);
            console.log('  ✅ All exercises fetched successfully');
        } else {
            console.log('  ❌ Failed to fetch exercises');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 2: Filter by category
    console.log('\n✓ Testing GET /exercises?category=Push');
    try {
        const result = await makeRequest('GET', '/exercises?category=Push', null, accessToken);
        console.log(`  Status: ${result.status}`);
        console.log(`  Response: ${result.data.length} Push exercises`);

        if (result.status === 200) {
            const allPush = result.data.every(ex => ex.category === 'Push');
            if (allPush) {
                console.log(`  Sample: ${result.data.slice(0, 3).map(ex => ex.name).join(', ')}`);
                console.log('  ✅ Category filter working correctly');
            } else {
                console.log('  ❌ Category filter not working correctly');
            }
        } else {
            console.log('  ❌ Failed to filter by category');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 3: Search by name
    console.log('\n✓ Testing GET /exercises?search=squat');
    try {
        const result = await makeRequest('GET', '/exercises?search=squat', null, accessToken);
        console.log(`  Status: ${result.status}`);
        console.log(`  Response: ${result.data.length} exercises matching "squat"`);

        if (result.status === 200 && result.data.length > 0) {
            console.log(`  Found: ${result.data.map(ex => ex.name).join(', ')}`);
            console.log('  ✅ Search functionality working');
        } else {
            console.log('  ❌ Search failed');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 4: Verify response includes all required fields
    console.log('\n✓ Testing response includes all required fields');
    try {
        const result = await makeRequest('GET', '/exercises?search=squat', null, accessToken);

        if (result.status === 200 && result.data.length > 0) {
            const exercise = result.data[0];
            const requiredFields = ['id', 'name', 'category', 'is_custom', 'created_at', 'updated_at'];
            const hasAllFields = requiredFields.every(field => field in exercise);

            if (hasAllFields) {
                console.log(`  ✅ All required fields present: ${requiredFields.join(', ')}`);
            } else {
                console.log('  ❌ Missing required fields');
            }
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 5: Create custom exercise
    console.log('\n✓ Testing POST /exercises (create custom exercise)');
    try {
        const customExerciseName = `My Custom Exercise ${timestamp}`;
        const result = await makeRequest('POST', '/exercises', {
            name: customExerciseName,
            category: 'Accessories',
            primary_muscle: 'Forearms',
            secondary_muscles: ['Biceps']
        }, accessToken);

        console.log(`  Status: ${result.status}`);
        console.log(`  Response:`, JSON.stringify(result.data, null, 2));

        if (result.status === 201 && result.data.is_custom === true) {
            customExerciseId = result.data.id;
            console.log('  ✅ Custom exercise created successfully');
        } else {
            console.log('  ❌ Failed to create custom exercise');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 6: Verify custom exercise appears in user's list
    console.log('\n✓ Testing GET /exercises (custom exercise in list)');
    try {
        const result = await makeRequest('GET', '/exercises', null, accessToken);
        const customExercises = result.data.filter(ex => ex.is_custom === true);

        console.log(`  Status: ${result.status}`);
        console.log(`  Custom exercises found: ${customExercises.length}`);

        if (customExercises.length > 0) {
            console.log(`  Custom exercises: ${customExercises.map(ex => ex.name).join(', ')}`);
            console.log('  ✅ Custom exercise visible in user\'s list');
        } else {
            console.log('  ❌ Custom exercise not found in list');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 7: Create another user and verify they can't see custom exercise
    console.log('\n✓ Testing custom exercise isolation (other user)');
    try {
        // Register second user
        const testEmail2 = `exercises2_${timestamp}@example.com`;
        await makeRequest('POST', '/auth/register', {
            email: testEmail2,
            password: testPassword
        });

        const loginResult2 = await makeRequest('POST', '/auth/login', {
            email: testEmail2,
            password: testPassword
        });

        const accessToken2 = loginResult2.data.access_token;

        // Try to fetch exercises as second user
        const result = await makeRequest('GET', '/exercises', null, accessToken2);
        const customExercises = result.data.filter(ex => ex.is_custom === true);

        console.log(`  Status: ${result.status}`);
        console.log(`  Custom exercises visible to second user: ${customExercises.length}`);

        if (customExercises.length === 0) {
            console.log('  ✅ Custom exercises properly isolated per user');
        } else {
            console.log('  ❌ Other user can see first user\'s custom exercises');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    console.log('\n' + '='.repeat(50));
    console.log('\nExercise endpoint tests complete!\n');
}

// Run tests
testExercises().catch(console.error);
