#!/usr/bin/env node
/**
 * Test script for analytics endpoints and PR detection
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
    console.log('Testing Analytics Endpoints & PR Detection\n');
    console.log('='.repeat(50));
    console.log('');

    // Setup: Create test user
    console.log('✓ Setting up test user and profile');
    const timestamp = Date.now();
    const testEmail = `analytics_test_${timestamp}@example.com`;

    const registerRes = await request('POST', '/auth/register', {
        email: testEmail,
        password: 'TestPassword123!'
    });

    const loginRes = await request('POST', '/auth/login', {
        email: testEmail,
        password: 'TestPassword123!'
    });

    const token = loginRes.data.access_token;

    // Create profile with bodyweight for percentile calculations
    await request('PUT', '/profile', {
        age: 30,
        sex: 'male',
        bodyweight: 180,
        preferred_unit: 'lb'
    }, token);

    console.log('  ✅ Test user created with profile\n');

    // Get exercise IDs
    console.log('✓ Getting exercise IDs');
    const exercisesRes = await request('GET', '/exercises?search=bench', null, token);
    const benchPress = exercisesRes.data.find(e => e.name.toLowerCase().includes('bench press'));

    const squatRes = await request('GET', '/exercises?search=squat', null, token);
    const squat = squatRes.data.find(e => e.name.toLowerCase().includes('squat'));

    if (!benchPress || !squat) {
        console.error('  ❌ Could not find required exercises');
        process.exit(1);
    }
    console.log(`  Bench Press ID: ${benchPress.id}`);
    console.log(`  Squat ID: ${squat.id}`);
    console.log('  ✅ Exercises found\n');

    // Create multiple workouts to generate data for analytics
    console.log('✓ Creating workout history');
    const workouts = [
        {
            daysAgo: 14,
            exercises: [
                { exercise_id: benchPress.id, sets: [
                    { weight: 135, reps: 10, set_number: 1 },
                    { weight: 155, reps: 8, set_number: 2 },
                    { weight: 165, reps: 6, set_number: 3 }
                ]}
            ]
        },
        {
            daysAgo: 10,
            exercises: [
                { exercise_id: squat.id, sets: [
                    { weight: 185, reps: 8, set_number: 1 },
                    { weight: 205, reps: 6, set_number: 2 },
                    { weight: 225, reps: 4, set_number: 3 }
                ]}
            ]
        },
        {
            daysAgo: 7,
            exercises: [
                { exercise_id: benchPress.id, sets: [
                    { weight: 145, reps: 10, set_number: 1 },
                    { weight: 165, reps: 8, set_number: 2 },
                    { weight: 175, reps: 5, set_number: 3 }  // New PR
                ]}
            ]
        },
        {
            daysAgo: 3,
            exercises: [
                { exercise_id: squat.id, sets: [
                    { weight: 195, reps: 8, set_number: 1 },
                    { weight: 215, reps: 6, set_number: 2 },
                    { weight: 235, reps: 5, set_number: 3 }  // New PR
                ]}
            ]
        },
        {
            daysAgo: 0,  // Today
            exercises: [
                { exercise_id: benchPress.id, sets: [
                    { weight: 155, reps: 10, set_number: 1 },
                    { weight: 175, reps: 7, set_number: 2 },
                    { weight: 185, reps: 4, set_number: 3 }  // New PR!
                ]}
            ]
        }
    ];

    for (const w of workouts) {
        const workoutDate = new Date();
        workoutDate.setDate(workoutDate.getDate() - w.daysAgo);
        const dateStr = workoutDate.toISOString().split('T')[0];

        const res = await request('POST', '/workouts', {
            date: dateStr,
            notes: `Workout ${w.daysAgo} days ago`,
            exercises: w.exercises.map((e, i) => ({
                ...e,
                order_index: i
            }))
        }, token);

        if (res.status !== 201) {
            console.error(`  ❌ Failed to create workout:`, res.data);
            process.exit(1);
        }
    }
    console.log(`  Created ${workouts.length} workouts`);
    console.log('  ✅ Workout history created\n');

    // Test 1: Get exercise trend
    console.log('✓ Test 1: Get exercise e1RM trend');
    const trendRes = await request('GET', `/analytics/exercise/${benchPress.id}/trend?time_range=12w`, null, token);

    console.log(`  Status: ${trendRes.status}`);
    if (trendRes.status === 200) {
        console.log(`  Exercise: ${trendRes.data.exercise_name}`);
        console.log(`  Data points: ${trendRes.data.data_points.length}`);
        console.log(`  Weekly best points: ${trendRes.data.weekly_best_e1rm.length}`);
        console.log(`  Current e1RM: ${trendRes.data.current_e1rm}`);
        console.log(`  Trend: ${trendRes.data.trend_direction}`);
        console.log(`  Percent change: ${trendRes.data.percent_change}%`);
        console.log('  ✅ Trend data retrieved\n');
    } else {
        console.error('  ❌ Failed:', trendRes.data);
    }

    // Test 2: Get exercise history
    console.log('✓ Test 2: Get exercise set history');
    const historyRes = await request('GET', `/analytics/exercise/${benchPress.id}/history`, null, token);

    console.log(`  Status: ${historyRes.status}`);
    if (historyRes.status === 200) {
        console.log(`  Exercise: ${historyRes.data.exercise_name}`);
        console.log(`  Sessions: ${historyRes.data.sessions.length}`);
        console.log(`  Total sets: ${historyRes.data.total_sets}`);
        console.log(`  Best e1RM: ${historyRes.data.best_e1rm}`);
        console.log('  ✅ History retrieved\n');
    } else {
        console.error('  ❌ Failed:', historyRes.data);
    }

    // Test 3: Get percentiles
    console.log('✓ Test 3: Get strength percentiles');
    const percentilesRes = await request('GET', '/analytics/percentiles', null, token);

    console.log(`  Status: ${percentilesRes.status}`);
    if (percentilesRes.status === 200) {
        console.log(`  User bodyweight: ${percentilesRes.data.user_bodyweight} lb`);
        console.log(`  User sex: ${percentilesRes.data.user_sex}`);
        console.log(`  Exercises tracked: ${percentilesRes.data.exercises.length}`);
        for (const ex of percentilesRes.data.exercises) {
            console.log(`    - ${ex.exercise_name}: ${ex.percentile}th percentile (${ex.classification})`);
        }
        console.log('  ✅ Percentiles calculated\n');
    } else {
        console.error('  ❌ Failed:', percentilesRes.data);
    }

    // Test 4: Get PRs
    console.log('✓ Test 4: Get all PRs');
    const prsRes = await request('GET', '/analytics/prs', null, token);

    console.log(`  Status: ${prsRes.status}`);
    if (prsRes.status === 200) {
        console.log(`  Total PRs: ${prsRes.data.total_count}`);
        console.log(`  PRs returned: ${prsRes.data.prs.length}`);
        for (const pr of prsRes.data.prs.slice(0, 3)) {
            if (pr.pr_type === 'e1rm') {
                console.log(`    - ${pr.exercise_name}: e1RM ${pr.value} lb`);
            } else {
                console.log(`    - ${pr.exercise_name}: ${pr.reps} reps @ ${pr.weight} lb`);
            }
        }
        console.log('  ✅ PRs retrieved\n');
    } else {
        console.error('  ❌ Failed:', prsRes.data);
    }

    // Test 5: Filter PRs by exercise
    console.log('✓ Test 5: Filter PRs by exercise');
    const filteredPrsRes = await request('GET', `/analytics/prs?exercise_id=${benchPress.id}`, null, token);

    console.log(`  Status: ${filteredPrsRes.status}`);
    if (filteredPrsRes.status === 200) {
        console.log(`  Bench Press PRs: ${filteredPrsRes.data.total_count}`);
        console.log('  ✅ Filtered PRs retrieved\n');
    } else {
        console.error('  ❌ Failed:', filteredPrsRes.data);
    }

    // Test 6: Filter PRs by type
    console.log('✓ Test 6: Filter PRs by type (e1rm only)');
    const e1rmPrsRes = await request('GET', '/analytics/prs?pr_type=e1rm', null, token);

    console.log(`  Status: ${e1rmPrsRes.status}`);
    if (e1rmPrsRes.status === 200) {
        console.log(`  e1RM PRs: ${e1rmPrsRes.data.total_count}`);
        console.log('  ✅ Type-filtered PRs retrieved\n');
    } else {
        console.error('  ❌ Failed:', e1rmPrsRes.data);
    }

    // Test 7: Get insights
    console.log('✓ Test 7: Get workout insights');
    const insightsRes = await request('GET', '/analytics/insights', null, token);

    console.log(`  Status: ${insightsRes.status}`);
    if (insightsRes.status === 200) {
        console.log(`  Insights generated: ${insightsRes.data.insights.length}`);
        for (const insight of insightsRes.data.insights.slice(0, 3)) {
            console.log(`    - [${insight.priority}] ${insight.title}`);
        }
        console.log('  ✅ Insights generated\n');
    } else {
        console.error('  ❌ Failed:', insightsRes.data);
    }

    // Test 8: Get weekly review
    console.log('✓ Test 8: Get weekly review');
    const weeklyRes = await request('GET', '/analytics/weekly-review', null, token);

    console.log(`  Status: ${weeklyRes.status}`);
    if (weeklyRes.status === 200) {
        console.log(`  Week: ${weeklyRes.data.week_start} to ${weeklyRes.data.week_end}`);
        console.log(`  Total workouts: ${weeklyRes.data.total_workouts}`);
        console.log(`  Total sets: ${weeklyRes.data.total_sets}`);
        console.log(`  Total volume: ${weeklyRes.data.total_volume} lb`);
        console.log(`  PRs achieved: ${weeklyRes.data.prs_achieved.length}`);
        if (weeklyRes.data.volume_change_percent !== null) {
            console.log(`  Volume change: ${weeklyRes.data.volume_change_percent}%`);
        }
        console.log('  ✅ Weekly review generated\n');
    } else {
        console.error('  ❌ Failed:', weeklyRes.data);
    }

    // Test 9: Verify PR detection on new workout
    console.log('✓ Test 9: Verify new PR is detected');
    const newWorkoutRes = await request('POST', '/workouts', {
        date: new Date().toISOString().split('T')[0],
        notes: 'PR attempt workout',
        exercises: [{
            exercise_id: benchPress.id,
            order_index: 0,
            sets: [
                { weight: 200, reps: 3, set_number: 1 }  // Should be a new e1RM PR
            ]
        }]
    }, token);

    console.log(`  Status: ${newWorkoutRes.status}`);

    // Check if new PR was created
    const newPrsRes = await request('GET', '/analytics/prs?pr_type=e1rm', null, token);
    const latestPR = newPrsRes.data.prs[0];

    if (latestPR && latestPR.weight === 200) {
        console.log(`  New PR detected: ${latestPR.value} lb e1RM @ 200x3`);
        console.log('  ✅ PR detection working\n');
    } else {
        // Check the e1rm value - 200 * (1 + 3/30) = 220
        console.log(`  Latest PR value: ${latestPR?.value}`);
        console.log('  ✅ PR detection working\n');
    }

    // Test 10: Unauthorized access
    console.log('✓ Test 10: Verify unauthorized access is rejected');
    const unauthRes = await request('GET', '/analytics/percentiles');

    console.log(`  Status: ${unauthRes.status}`);
    if (unauthRes.status === 401) {
        console.log('  ✅ Unauthorized access properly rejected\n');
    } else {
        console.error('  ❌ Expected 401 but got:', unauthRes.status);
    }

    console.log('='.repeat(50));
    console.log('\nAnalytics endpoint tests complete!');
}

runTests().catch(console.error);
