#!/usr/bin/env node
/**
 * Test script for bodyweight tracking endpoints
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
    console.log('Testing Bodyweight Tracking Endpoints\n');
    console.log('='.repeat(50));
    console.log('');

    // Setup: Create test user and get token
    console.log('✓ Setting up test user and authentication');
    const timestamp = Date.now();
    const testEmail = `bodyweight_test_${timestamp}@example.com`;

    const registerRes = await request('POST', '/auth/register', {
        email: testEmail,
        password: 'TestPassword123!'
    });

    if (registerRes.status !== 201) {
        console.error('  ❌ Failed to create test user:', registerRes.data);
        process.exit(1);
    }

    const loginRes = await request('POST', '/auth/login', {
        email: testEmail,
        password: 'TestPassword123!'
    });

    if (loginRes.status !== 200) {
        console.error('  ❌ Failed to login:', loginRes.data);
        process.exit(1);
    }

    const token = loginRes.data.access_token;
    console.log('  ✅ Test user created, auth token obtained\n');

    // Test 1: Log initial bodyweight entry
    console.log('✓ Test 1: Log initial bodyweight entry');
    const today = new Date().toISOString().split('T')[0];
    const entry1 = await request('POST', '/bodyweight', {
        date: today,
        weight: 165.5,
        weight_unit: 'lb',
        source: 'manual'
    }, token);

    console.log(`  Status: ${entry1.status}`);
    if (entry1.status === 201) {
        console.log(`  Weight: ${entry1.data.weight_lb} lb`);
        console.log(`  Date: ${entry1.data.date}`);
        console.log('  ✅ Bodyweight entry created\n');
    } else {
        console.error('  ❌ Failed:', entry1.data);
        process.exit(1);
    }

    // Test 2: Log entries for multiple days
    console.log('✓ Test 2: Log bodyweight entries for multiple days');
    const weights = [
        { daysAgo: 1, weight: 166.0 },
        { daysAgo: 2, weight: 165.8 },
        { daysAgo: 3, weight: 166.2 },
        { daysAgo: 4, weight: 165.5 },
        { daysAgo: 5, weight: 165.0 },
        { daysAgo: 6, weight: 164.8 },
        { daysAgo: 7, weight: 165.2 },
    ];

    for (const w of weights) {
        const date = new Date();
        date.setDate(date.getDate() - w.daysAgo);
        const dateStr = date.toISOString().split('T')[0];

        const res = await request('POST', '/bodyweight', {
            date: dateStr,
            weight: w.weight,
            weight_unit: 'lb'
        }, token);

        if (res.status !== 201) {
            console.error(`  ❌ Failed to log weight for ${dateStr}:`, res.data);
            process.exit(1);
        }
    }
    console.log(`  Created ${weights.length} additional entries`);
    console.log('  ✅ Multiple entries logged\n');

    // Test 3: Update entry for same date (upsert)
    console.log('✓ Test 3: Update entry for same date (upsert behavior)');
    const updateRes = await request('POST', '/bodyweight', {
        date: today,
        weight: 165.0,
        weight_unit: 'lb'
    }, token);

    console.log(`  Status: ${updateRes.status}`);
    console.log(`  Updated weight: ${updateRes.data.weight_lb} lb`);
    if (updateRes.data.weight_lb === 165.0) {
        console.log('  ✅ Entry updated correctly\n');
    } else {
        console.error('  ❌ Weight not updated correctly');
        process.exit(1);
    }

    // Test 4: Get bodyweight history
    console.log('✓ Test 4: Get bodyweight history');
    const historyRes = await request('GET', '/bodyweight', null, token);

    console.log(`  Status: ${historyRes.status}`);
    console.log(`  Total entries: ${historyRes.data.total_entries}`);
    console.log(`  Entries returned: ${historyRes.data.entries.length}`);
    if (historyRes.data.rolling_average_7day) {
        console.log(`  7-day rolling average: ${historyRes.data.rolling_average_7day} lb`);
    }
    console.log(`  Trend: ${historyRes.data.trend}`);
    console.log('  ✅ History retrieved with analytics\n');

    // Test 5: Test kg unit conversion
    console.log('✓ Test 5: Log entry in kg (unit conversion)');
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    const kgRes = await request('POST', '/bodyweight', {
        date: yesterday.toISOString().split('T')[0],
        weight: 75.0,
        weight_unit: 'kg'
    }, token);

    console.log(`  Status: ${kgRes.status}`);
    console.log(`  Input: 75 kg`);
    console.log(`  Stored as: ${kgRes.data.weight_lb} lb`);
    // 75 kg = 165.35 lb approximately
    if (kgRes.data.weight_lb > 165 && kgRes.data.weight_lb < 166) {
        console.log('  ✅ Unit conversion correct\n');
    } else {
        console.error('  ❌ Unit conversion incorrect');
    }

    // Test 6: Get specific entry by ID
    console.log('✓ Test 6: Get specific bodyweight entry');
    const entryId = entry1.data.id;
    const getRes = await request('GET', `/bodyweight/${entryId}`, null, token);

    console.log(`  Status: ${getRes.status}`);
    if (getRes.status === 200) {
        console.log(`  Entry ID: ${getRes.data.id}`);
        console.log(`  Weight: ${getRes.data.weight_lb} lb`);
        console.log('  ✅ Entry retrieved successfully\n');
    } else {
        console.error('  ❌ Failed to get entry:', getRes.data);
    }

    // Test 7: Delete bodyweight entry
    console.log('✓ Test 7: Delete bodyweight entry');
    const deleteRes = await request('DELETE', `/bodyweight/${entryId}`, null, token);

    console.log(`  Status: ${deleteRes.status}`);
    if (deleteRes.status === 204) {
        console.log('  ✅ Entry deleted successfully\n');
    } else {
        console.error('  ❌ Failed to delete:', deleteRes.data);
    }

    // Test 8: Verify deleted entry returns 404
    console.log('✓ Test 8: Verify deleted entry returns 404');
    const verifyRes = await request('GET', `/bodyweight/${entryId}`, null, token);

    console.log(`  Status: ${verifyRes.status}`);
    if (verifyRes.status === 404) {
        console.log('  ✅ Deleted entry properly returns 404\n');
    } else {
        console.error('  ❌ Expected 404 but got:', verifyRes.status);
    }

    // Test 9: Verify history count decreased
    console.log('✓ Test 9: Verify history count after deletion');
    const history2Res = await request('GET', '/bodyweight', null, token);

    console.log(`  Total entries now: ${history2Res.data.total_entries}`);
    if (history2Res.data.total_entries === historyRes.data.total_entries - 1) {
        console.log('  ✅ Entry count correctly decreased\n');
    } else {
        console.error('  ❌ Entry count mismatch');
    }

    // Test 10: Unauthorized access
    console.log('✓ Test 10: Verify unauthorized access is rejected');
    const unauthRes = await request('GET', '/bodyweight');

    console.log(`  Status: ${unauthRes.status}`);
    if (unauthRes.status === 401) {
        console.log('  ✅ Unauthorized access properly rejected\n');
    } else {
        console.error('  ❌ Expected 401 but got:', unauthRes.status);
    }

    console.log('='.repeat(50));
    console.log('\nBodyweight tracking endpoint tests complete!');
}

runTests().catch(console.error);
