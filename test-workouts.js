#!/usr/bin/env node

/**
 * Test workout endpoints
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

async function testWorkouts() {
    console.log('Testing Workout Endpoints\n');
    console.log('='.repeat(50));

    // Generate unique email for testing
    const timestamp = Date.now();
    const testEmail = `workouts${timestamp}@example.com`;
    const testPassword = 'TestPass123';

    let accessToken = '';
    let exerciseId1 = '';
    let exerciseId2 = '';
    let workoutId = '';

    // Setup: Create test user and get exercises
    console.log('\n✓ Setting up test user and fetching exercises');
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

        // Get exercises for workout
        const exercisesResult = await makeRequest('GET', '/exercises?search=squat', null, accessToken);
        if (exercisesResult.status === 200 && exercisesResult.data.length > 0) {
            exerciseId1 = exercisesResult.data[0].id;
        }

        const exercisesResult2 = await makeRequest('GET', '/exercises?search=bench', null, accessToken);
        if (exercisesResult2.status === 200 && exercisesResult2.data.length > 0) {
            exerciseId2 = exercisesResult2.data[0].id;
        }

        console.log(`  ✅ Test user created, exercises found: ${exerciseId1}, ${exerciseId2}`);
    } catch (error) {
        console.log('  ❌ Error:', error.message);
        return;
    }

    // Test 1: Create workout with multiple exercises
    console.log('\n✓ Testing POST /workouts (multiple exercises)');
    try {
        const workoutData = {
            date: new Date().toISOString(),
            duration_minutes: 60,
            session_rpe: 8,
            notes: 'Great workout!',
            exercises: [
                {
                    exercise_id: exerciseId1,
                    order_index: 0,
                    sets: [
                        { weight: 225, weight_unit: 'lb', reps: 5, rpe: 8, set_number: 1 },
                        { weight: 225, weight_unit: 'lb', reps: 5, rpe: 8, set_number: 2 },
                        { weight: 225, weight_unit: 'lb', reps: 5, rpe: 9, set_number: 3 }
                    ]
                },
                {
                    exercise_id: exerciseId2,
                    order_index: 1,
                    sets: [
                        { weight: 185, weight_unit: 'lb', reps: 8, rpe: 7, set_number: 1 },
                        { weight: 185, weight_unit: 'lb', reps: 8, rpe: 8, set_number: 2 },
                        { weight: 185, weight_unit: 'lb', reps: 6, rpe: 9, set_number: 3 }
                    ]
                }
            ]
        };

        const result = await makeRequest('POST', '/workouts', workoutData, accessToken);
        console.log(`  Status: ${result.status}`);

        if (result.status === 201) {
            workoutId = result.data.id;
            console.log(`  Workout ID: ${workoutId}`);
            console.log(`  Exercises: ${result.data.exercises.length}`);
            console.log(`  Total sets: ${result.data.exercises.reduce((sum, ex) => sum + ex.sets.length, 0)}`);

            // Check e1RM calculations
            const firstSet = result.data.exercises[0].sets[0];
            console.log(`  First set e1RM: ${firstSet.e1rm} (${firstSet.weight}lb x ${firstSet.reps} reps @ RPE ${firstSet.rpe})`);

            if (firstSet.e1rm > 0) {
                console.log('  ✅ Workout with multiple exercises created successfully');
            } else {
                console.log('  ❌ e1RM calculation failed');
            }
        } else {
            console.log('  ❌ Failed to create workout');
            console.log('  Response:', JSON.stringify(result.data, null, 2));
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 2: Create workout with single exercise
    console.log('\n✓ Testing POST /workouts (single exercise)');
    try {
        const workoutData = {
            date: new Date(Date.now() - 86400000).toISOString(), // Yesterday
            duration_minutes: 30,
            exercises: [
                {
                    exercise_id: exerciseId1,
                    order_index: 0,
                    sets: [
                        { weight: 135, weight_unit: 'lb', reps: 10, set_number: 1 },
                        { weight: 135, weight_unit: 'lb', reps: 10, set_number: 2 }
                    ]
                }
            ]
        };

        const result = await makeRequest('POST', '/workouts', workoutData, accessToken);
        console.log(`  Status: ${result.status}`);

        if (result.status === 201) {
            console.log(`  ✅ Workout with single exercise created`);
        } else {
            console.log('  ❌ Failed to create workout');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 3: Verify all data stored correctly
    console.log('\n✓ Testing GET /workouts/{id} (verify data)');
    try {
        const result = await makeRequest('GET', `/workouts/${workoutId}`, null, accessToken);
        console.log(`  Status: ${result.status}`);

        if (result.status === 200) {
            const workout = result.data;
            console.log(`  Workout date: ${workout.date}`);
            console.log(`  Duration: ${workout.duration_minutes} min`);
            console.log(`  Session RPE: ${workout.session_rpe}`);
            console.log(`  Notes: ${workout.notes}`);
            console.log(`  Exercises: ${workout.exercises.length}`);

            let allDataCorrect = true;
            workout.exercises.forEach((ex, idx) => {
                console.log(`  Exercise ${idx + 1}: ${ex.exercise_name} (${ex.sets.length} sets)`);
                ex.sets.forEach(set => {
                    if (!set.e1rm || set.e1rm <= 0) {
                        allDataCorrect = false;
                    }
                });
            });

            if (allDataCorrect) {
                console.log('  ✅ All workout data stored and retrieved correctly');
            } else {
                console.log('  ❌ Some data missing or incorrect');
            }
        } else {
            console.log('  ❌ Failed to fetch workout');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 4: Return complete workout with IDs
    console.log('\n✓ Testing response includes all required IDs');
    try {
        const result = await makeRequest('GET', `/workouts/${workoutId}`, null, accessToken);

        if (result.status === 200) {
            const workout = result.data;
            const hasWorkoutId = !!workout.id;
            const hasExerciseIds = workout.exercises.every(ex => !!ex.id && !!ex.exercise_id);
            const hasSetIds = workout.exercises.every(ex =>
                ex.sets.every(set => !!set.id)
            );

            if (hasWorkoutId && hasExerciseIds && hasSetIds) {
                console.log('  ✅ All IDs present in response');
            } else {
                console.log('  ❌ Some IDs missing');
            }
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 5: List workouts (first page)
    console.log('\n✓ Testing GET /workouts (first page)');
    try {
        const result = await makeRequest('GET', '/workouts?limit=10&offset=0', null, accessToken);
        console.log(`  Status: ${result.status}`);

        if (result.status === 200) {
            console.log(`  Workouts returned: ${result.data.length}`);
            if (result.data.length > 0) {
                const workout = result.data[0];
                console.log(`  First workout: ${workout.exercise_count} exercises, ${workout.total_sets} sets`);
                console.log('  ✅ Workout list fetched successfully');
            } else {
                console.log('  ❌ No workouts returned');
            }
        } else {
            console.log('  ❌ Failed to fetch workouts');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 6: Test pagination
    console.log('\n✓ Testing GET /workouts (pagination)');
    try {
        const result1 = await makeRequest('GET', '/workouts?limit=1&offset=0', null, accessToken);
        const result2 = await makeRequest('GET', '/workouts?limit=1&offset=1', null, accessToken);

        console.log(`  Page 1 status: ${result1.status}, workouts: ${result1.data.length}`);
        console.log(`  Page 2 status: ${result2.status}, workouts: ${result2.data.length}`);

        if (result1.status === 200 && result2.status === 200) {
            if (result1.data.length === 1 && result2.data.length === 1) {
                const differentWorkouts = result1.data[0].id !== result2.data[0].id;
                if (differentWorkouts) {
                    console.log('  ✅ Pagination working correctly');
                } else {
                    console.log('  ❌ Pagination returning same workout');
                }
            } else {
                console.log('  ⚠️  Not enough workouts to test pagination properly');
            }
        } else {
            console.log('  ❌ Failed to fetch paginated results');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 7: Verify workouts ordered by date descending
    console.log('\n✓ Testing GET /workouts (date ordering)');
    try {
        const result = await makeRequest('GET', '/workouts?limit=10&offset=0', null, accessToken);

        if (result.status === 200 && result.data.length >= 2) {
            const dates = result.data.map(w => new Date(w.date).getTime());
            const isDescending = dates.every((date, idx) => {
                if (idx === 0) return true;
                return date <= dates[idx - 1];
            });

            if (isDescending) {
                console.log('  ✅ Workouts correctly ordered by date descending');
            } else {
                console.log('  ❌ Workouts not in correct order');
            }
        } else {
            console.log('  ⚠️  Not enough workouts to test ordering');
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    // Test 8: Verify workout data is complete
    console.log('\n✓ Testing workout data completeness');
    try {
        const result = await makeRequest('GET', `/workouts/${workoutId}`, null, accessToken);

        if (result.status === 200) {
            const workout = result.data;
            const requiredFields = ['id', 'user_id', 'date', 'exercises', 'created_at', 'updated_at'];
            const hasAllFields = requiredFields.every(field => field in workout);

            const exercisesComplete = workout.exercises.every(ex =>
                'id' in ex && 'exercise_name' in ex && 'sets' in ex
            );

            const setsComplete = workout.exercises.every(ex =>
                ex.sets.every(set => 'id' in set && 'weight' in set && 'reps' in set && 'e1rm' in set)
            );

            if (hasAllFields && exercisesComplete && setsComplete) {
                console.log('  ✅ Workout data is complete with all required fields');
            } else {
                console.log('  ❌ Some required fields missing');
            }
        }
    } catch (error) {
        console.log('  ❌ Error:', error.message);
    }

    console.log('\n' + '='.repeat(50));
    console.log('\nWorkout endpoint tests complete!\n');
}

// Run tests
testWorkouts().catch(console.error);
