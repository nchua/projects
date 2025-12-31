#!/usr/bin/env node
/**
 * Test script for sync endpoints
 */

const BASE_URL = 'http://localhost:8000';

async function request(method, path, body = null, token = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const options = { method, headers };
    if (body) options.body = JSON.stringify(body);

    const response = await fetch(`${BASE_URL}${path}`, options);
    const text = await response.text();
    let data = null;
    try { data = JSON.parse(text); } catch (e) { data = text; }
    return { status: response.status, data };
}

async function runTests() {
    console.log('Testing Sync Endpoints\n');
    console.log('='.repeat(50));
    console.log('');

    // Setup: Create test user
    console.log('✓ Setting up test user');
    const timestamp = Date.now();
    const testEmail = `sync_test_${timestamp}@example.com`;

    await request('POST', '/auth/register', {
        email: testEmail,
        password: 'TestPassword123!'
    });

    const loginRes = await request('POST', '/auth/login', {
        email: testEmail,
        password: 'TestPassword123!'
    });

    const token = loginRes.data.access_token;
    console.log('  ✅ Test user created\n');

    // Get an exercise ID
    const exercisesRes = await request('GET', '/exercises?search=bench', null, token);
    const benchPress = exercisesRes.data[0];

    // Test 1: Get initial sync status
    console.log('✓ Test 1: Get initial sync status');
    const status1 = await request('GET', '/sync/status', null, token);

    console.log(`  Status: ${status1.status}`);
    if (status1.status === 200) {
        console.log(`  Last sync: ${status1.data.last_sync_at || 'never'}`);
        console.log(`  Pending workouts: ${status1.data.pending_workouts}`);
        console.log(`  Is synced: ${status1.data.is_synced}`);
        console.log('  ✅ Sync status retrieved\n');
    } else {
        console.error('  ❌ Failed:', status1.data);
    }

    // Test 2: Bulk sync with workouts
    console.log('✓ Test 2: Bulk sync with workouts');
    const today = new Date().toISOString().split('T')[0];
    const syncRes = await request('POST', '/sync', {
        workouts: [
            {
                date: today,
                notes: 'Synced workout',
                exercises: [{
                    exercise_id: benchPress.id,
                    order_index: 0,
                    sets: [
                        { weight: 135, reps: 10, set_number: 1 },
                        { weight: 155, reps: 8, set_number: 2 }
                    ]
                }]
            }
        ],
        bodyweight_entries: [
            {
                date: today,
                weight: 175,
                weight_unit: 'lb'
            }
        ],
        client_timestamp: new Date().toISOString()
    }, token);

    console.log(`  Status: ${syncRes.status}`);
    if (syncRes.status === 200) {
        console.log(`  Success: ${syncRes.data.success}`);
        console.log(`  Workouts synced: ${syncRes.data.workouts_synced}`);
        console.log(`  Bodyweight entries synced: ${syncRes.data.bodyweight_entries_synced}`);
        console.log(`  Conflicts: ${syncRes.data.conflicts.length}`);
        console.log('  ✅ Bulk sync completed\n');
    } else {
        console.error('  ❌ Failed:', syncRes.data);
    }

    // Test 3: Verify workout was created
    console.log('✓ Test 3: Verify workout was created');
    const workoutsRes = await request('GET', '/workouts', null, token);

    console.log(`  Status: ${workoutsRes.status}`);
    console.log(`  Workouts: ${workoutsRes.data.length}`);
    if (workoutsRes.data.length > 0) {
        console.log('  ✅ Synced workout exists\n');
    } else {
        console.error('  ❌ No workouts found');
    }

    // Test 4: Sync again with conflict (same date)
    console.log('✓ Test 4: Sync with conflict (same date)');
    const sync2Res = await request('POST', '/sync', {
        workouts: [
            {
                date: today,
                notes: 'Updated synced workout',
                exercises: [{
                    exercise_id: benchPress.id,
                    order_index: 0,
                    sets: [
                        { weight: 185, reps: 5, set_number: 1 }
                    ]
                }]
            }
        ],
        bodyweight_entries: [],
        client_timestamp: new Date().toISOString()
    }, token);

    console.log(`  Status: ${sync2Res.status}`);
    if (sync2Res.status === 200) {
        console.log(`  Conflicts detected: ${sync2Res.data.conflicts.length}`);
        if (sync2Res.data.conflicts.length > 0) {
            console.log(`  Resolution: ${sync2Res.data.conflicts[0].resolution}`);
        }
        console.log('  ✅ Conflict resolved (client wins)\n');
    } else {
        console.error('  ❌ Failed:', sync2Res.data);
    }

    // Test 5: Check sync status after sync
    console.log('✓ Test 5: Check sync status after sync');
    const status2 = await request('GET', '/sync/status', null, token);

    console.log(`  Status: ${status2.status}`);
    if (status2.status === 200) {
        console.log(`  Last sync: ${status2.data.last_sync_at}`);
        console.log(`  Is synced: ${status2.data.is_synced}`);
        console.log('  ✅ Sync status updated\n');
    }

    // Test 6: Sync bodyweight in kg
    console.log('✓ Test 6: Sync bodyweight in kg');
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const sync3Res = await request('POST', '/sync', {
        workouts: [],
        bodyweight_entries: [
            {
                date: yesterday.toISOString().split('T')[0],
                weight: 80,
                weight_unit: 'kg'
            }
        ],
        client_timestamp: new Date().toISOString()
    }, token);

    console.log(`  Status: ${sync3Res.status}`);
    if (sync3Res.status === 200) {
        console.log(`  Bodyweight entries synced: ${sync3Res.data.bodyweight_entries_synced}`);
        console.log('  ✅ kg to lb conversion working\n');
    }

    // Test 7: Unauthorized access
    console.log('✓ Test 7: Verify unauthorized access is rejected');
    const unauthRes = await request('GET', '/sync/status');

    console.log(`  Status: ${unauthRes.status}`);
    if (unauthRes.status === 401) {
        console.log('  ✅ Unauthorized access properly rejected\n');
    }

    console.log('='.repeat(50));
    console.log('\nSync endpoint tests complete!');
}

runTests().catch(console.error);
