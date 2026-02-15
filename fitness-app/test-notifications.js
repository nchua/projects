/**
 * Test script for notification endpoints
 * Usage: node test-notifications.js
 */

const BASE_URL = process.env.API_BASE_URL || 'https://backend-production-e316.up.railway.app';
const EMAIL = process.env.SEED_USER_EMAIL || 'test@example.com';
const PASSWORD = process.env.SEED_USER_PASSWORD || 'TestPass123!';

let accessToken = null;

async function request(method, path, body = null) {
    const opts = {
        method,
        headers: {
            'Content-Type': 'application/json',
        },
    };
    if (accessToken) {
        opts.headers['Authorization'] = `Bearer ${accessToken}`;
    }
    if (body) {
        opts.body = JSON.stringify(body);
    }

    const res = await fetch(`${BASE_URL}${path}`, opts);
    const data = await res.json();
    return { status: res.status, data };
}

async function login() {
    console.log(`\n=== Logging in as ${EMAIL} ===`);
    const { status, data } = await request('POST', '/auth/login', {
        email: EMAIL,
        password: PASSWORD,
    });
    if (status === 200) {
        accessToken = data.access_token;
        console.log('✓ Logged in successfully');
    } else {
        console.error('✗ Login failed:', data);
        process.exit(1);
    }
}

async function testRegisterDeviceToken() {
    console.log('\n=== Register Device Token ===');
    const { status, data } = await request('POST', '/notifications/device-token', {
        token: 'abc123def456test_token_for_testing',
        platform: 'ios',
    });
    console.log(`Status: ${status}`);
    console.log('Response:', JSON.stringify(data, null, 2));
    return status === 200;
}

async function testGetPreferences() {
    console.log('\n=== Get Notification Preferences ===');
    const { status, data } = await request('GET', '/notifications/preferences');
    console.log(`Status: ${status}`);
    console.log(`Preference count: ${data.preferences?.length}`);
    if (data.preferences?.length > 0) {
        console.log('First preference:', JSON.stringify(data.preferences[0], null, 2));
        console.log('All types:', data.preferences.map(p => p.notification_type).join(', '));
    }
    return status === 200;
}

async function testUpdatePreferences() {
    console.log('\n=== Update Preferences (disable streak_at_risk) ===');
    const { status, data } = await request('PUT', '/notifications/preferences', {
        preferences: [
            { notification_type: 'streak_at_risk', enabled: false },
        ],
    });
    console.log(`Status: ${status}`);
    const streakPref = data.preferences?.find(p => p.notification_type === 'streak_at_risk');
    console.log('streak_at_risk enabled:', streakPref?.enabled);

    // Re-enable it
    console.log('\n=== Re-enable streak_at_risk ===');
    const { status: s2, data: d2 } = await request('PUT', '/notifications/preferences', {
        preferences: [
            { notification_type: 'streak_at_risk', enabled: true },
        ],
    });
    const streakPref2 = d2.preferences?.find(p => p.notification_type === 'streak_at_risk');
    console.log('streak_at_risk enabled:', streakPref2?.enabled);

    return status === 200 && s2 === 200;
}

async function testDeactivateDeviceToken() {
    console.log('\n=== Deactivate Device Token ===');
    const { status, data } = await request('DELETE', '/notifications/device-token', {
        token: 'abc123def456test_token_for_testing',
        platform: 'ios',
    });
    console.log(`Status: ${status}`);
    console.log('Response:', JSON.stringify(data, null, 2));
    return status === 200;
}

async function main() {
    console.log('==============================================');
    console.log(' Notification Endpoints Test');
    console.log(`  Base URL: ${BASE_URL}`);
    console.log('==============================================');

    await login();

    const results = [];
    results.push(['Register Device Token', await testRegisterDeviceToken()]);
    results.push(['Get Preferences', await testGetPreferences()]);
    results.push(['Update Preferences', await testUpdatePreferences()]);
    results.push(['Deactivate Device Token', await testDeactivateDeviceToken()]);

    console.log('\n=== RESULTS ===');
    let allPassed = true;
    for (const [name, passed] of results) {
        console.log(`${passed ? '✓' : '✗'} ${name}`);
        if (!passed) allPassed = false;
    }

    console.log(`\n${allPassed ? '✓ All tests passed!' : '✗ Some tests failed'}`);
    process.exit(allPassed ? 0 : 1);
}

main().catch(err => {
    console.error('Fatal error:', err);
    process.exit(1);
});
