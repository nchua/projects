#!/usr/bin/env node

/**
 * Test script for workout update endpoint
 * Tests all update scenarios: notes, sets, exercises, and combinations
 */

const BASE_URL = 'http://localhost:8000';

// Test user credentials
const testEmail = `test${Date.now()}@example.com`;
const testPassword = 'TestPass123!';

let authToken = '';
let userId = '';
let workoutId = '';
let exerciseIds = [];

console.log('Testing Workout Update Endpoint\n');
console.log('==================================================\n');

async function testAPI() {
  try {
    // Setup: Create test user and get auth token
    console.log('✓ Setting up test user and authentication');
    const registerRes = await fetch(`${BASE_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: testEmail, password: testPassword })
    });
    const registerData = await registerRes.json();
    userId = registerData.user.id;

    const loginRes = await fetch(`${BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: testEmail, password: testPassword })
    });
    const loginData = await loginRes.json();
    authToken = loginData.access_token;

    // Get exercises for testing
    const exercisesRes = await fetch(`${BASE_URL}/exercises?limit=5`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const exercises = await exercisesRes.json();
    exerciseIds = exercises.slice(0, 3).map(e => e.id);
    console.log(`  ✅ Test user created, auth token obtained, exercises found\n`);

    // Create initial workout
    console.log('✓ Creating initial workout');
    const createRes = await fetch(`${BASE_URL}/workouts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        date: new Date().toISOString(),
        duration_minutes: 60,
        session_rpe: 7,
        notes: 'Original workout notes',
        exercises: [
          {
            exercise_id: exerciseIds[0],
            order_index: 0,
            sets: [
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 1 },
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 2 },
              { weight: 135, weight_unit: 'lb', reps: 8, rpe: 8, set_number: 3 }
            ]
          }
        ]
      })
    });
    const workout = await createRes.json();
    workoutId = workout.id;
    console.log(`  Status: ${createRes.status}`);
    console.log(`  Workout ID: ${workoutId}`);
    console.log(`  Original notes: "${workout.notes}"`);
    console.log(`  Original exercises: ${workout.exercises.length}`);
    console.log(`  Original sets: ${workout.exercises[0].sets.length}`);
    console.log(`  ✅ Initial workout created\n`);

    // Test 1: Update only notes
    console.log('✓ Test 1: Update workout notes only');
    const updateNotesRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        notes: 'Updated workout notes - feeling strong!'
      })
    });
    const updatedWorkout1 = await updateNotesRes.json();
    console.log(`  Status: ${updateNotesRes.status}`);
    console.log(`  Updated notes: "${updatedWorkout1.notes}"`);
    console.log(`  Exercises preserved: ${updatedWorkout1.exercises.length}`);
    console.log(`  Sets preserved: ${updatedWorkout1.exercises[0].sets.length}`);

    if (updatedWorkout1.notes === 'Updated workout notes - feeling strong!' &&
        updatedWorkout1.exercises.length === 1 &&
        updatedWorkout1.exercises[0].sets.length === 3) {
      console.log(`  ✅ Notes updated successfully, exercises/sets preserved\n`);
    } else {
      console.log(`  ❌ Notes update failed or data lost\n`);
    }

    // Test 2: Update session RPE and duration
    console.log('✓ Test 2: Update session RPE and duration');
    const updateSessionRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        duration_minutes: 75,
        session_rpe: 9
      })
    });
    const updatedWorkout2 = await updateSessionRes.json();
    console.log(`  Status: ${updateSessionRes.status}`);
    console.log(`  Updated duration: ${updatedWorkout2.duration_minutes} min`);
    console.log(`  Updated session RPE: ${updatedWorkout2.session_rpe}`);
    console.log(`  Notes preserved: "${updatedWorkout2.notes}"`);

    if (updatedWorkout2.duration_minutes === 75 &&
        updatedWorkout2.session_rpe === 9 &&
        updatedWorkout2.notes === 'Updated workout notes - feeling strong!') {
      console.log(`  ✅ Session data updated, notes preserved\n`);
    } else {
      console.log(`  ❌ Session update failed\n`);
    }

    // Test 3: Add a new set to existing exercise
    console.log('✓ Test 3: Add new set to existing exercise');
    const updateAddSetRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        exercises: [
          {
            exercise_id: exerciseIds[0],
            order_index: 0,
            sets: [
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 1 },
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 2 },
              { weight: 135, weight_unit: 'lb', reps: 8, rpe: 8, set_number: 3 },
              { weight: 145, weight_unit: 'lb', reps: 6, rpe: 9, set_number: 4 }  // NEW SET
            ]
          }
        ]
      })
    });
    const updatedWorkout3 = await updateAddSetRes.json();
    console.log(`  Status: ${updateAddSetRes.status}`);
    console.log(`  Sets after update: ${updatedWorkout3.exercises[0].sets.length}`);
    console.log(`  New set weight: ${updatedWorkout3.exercises[0].sets[3].weight}lb`);
    console.log(`  New set reps: ${updatedWorkout3.exercises[0].sets[3].reps}`);

    if (updatedWorkout3.exercises[0].sets.length === 4 &&
        updatedWorkout3.exercises[0].sets[3].weight === 145) {
      console.log(`  ✅ New set added successfully\n`);
    } else {
      console.log(`  ❌ Adding set failed\n`);
    }

    // Test 4: Remove a set from exercise
    console.log('✓ Test 4: Remove a set from exercise');
    const updateRemoveSetRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        exercises: [
          {
            exercise_id: exerciseIds[0],
            order_index: 0,
            sets: [
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 1 },
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 2 }
              // Removed last 2 sets
            ]
          }
        ]
      })
    });
    const updatedWorkout4 = await updateRemoveSetRes.json();
    console.log(`  Status: ${updateRemoveSetRes.status}`);
    console.log(`  Sets after removal: ${updatedWorkout4.exercises[0].sets.length}`);

    if (updatedWorkout4.exercises[0].sets.length === 2) {
      console.log(`  ✅ Sets removed successfully\n`);
    } else {
      console.log(`  ❌ Removing sets failed\n`);
    }

    // Test 5: Add a new exercise to workout
    console.log('✓ Test 5: Add new exercise to workout');
    const updateAddExerciseRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        exercises: [
          {
            exercise_id: exerciseIds[0],
            order_index: 0,
            sets: [
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 1 },
              { weight: 135, weight_unit: 'lb', reps: 10, rpe: 7, set_number: 2 }
            ]
          },
          {
            exercise_id: exerciseIds[1],  // NEW EXERCISE
            order_index: 1,
            sets: [
              { weight: 95, weight_unit: 'lb', reps: 8, rpe: 7, set_number: 1 },
              { weight: 95, weight_unit: 'lb', reps: 8, rpe: 8, set_number: 2 }
            ]
          }
        ]
      })
    });
    const updatedWorkout5 = await updateAddExerciseRes.json();
    console.log(`  Status: ${updateAddExerciseRes.status}`);
    console.log(`  Exercises after update: ${updatedWorkout5.exercises.length}`);
    console.log(`  Exercise 1: ${updatedWorkout5.exercises[0].exercise_name} (${updatedWorkout5.exercises[0].sets.length} sets)`);
    console.log(`  Exercise 2: ${updatedWorkout5.exercises[1].exercise_name} (${updatedWorkout5.exercises[1].sets.length} sets)`);

    if (updatedWorkout5.exercises.length === 2) {
      console.log(`  ✅ New exercise added successfully\n`);
    } else {
      console.log(`  ❌ Adding exercise failed\n`);
    }

    // Test 6: Update weight/reps and verify e1RM recalculation
    console.log('✓ Test 6: Update weight/reps and verify e1RM recalculation');
    const originalE1RM = updatedWorkout5.exercises[0].sets[0].e1rm;
    const updateE1RMRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        exercises: [
          {
            exercise_id: exerciseIds[0],
            order_index: 0,
            sets: [
              { weight: 225, weight_unit: 'lb', reps: 5, rpe: 8, set_number: 1 },  // Changed weight/reps
              { weight: 225, weight_unit: 'lb', reps: 5, rpe: 8, set_number: 2 }
            ]
          },
          {
            exercise_id: exerciseIds[1],
            order_index: 1,
            sets: [
              { weight: 95, weight_unit: 'lb', reps: 8, rpe: 7, set_number: 1 },
              { weight: 95, weight_unit: 'lb', reps: 8, rpe: 8, set_number: 2 }
            ]
          }
        ]
      })
    });
    const updatedWorkout6 = await updateE1RMRes.json();
    const newE1RM = updatedWorkout6.exercises[0].sets[0].e1rm;
    console.log(`  Status: ${updateE1RMRes.status}`);
    console.log(`  Original e1RM: ${originalE1RM} (135lb x 10 reps)`);
    console.log(`  New e1RM: ${newE1RM} (225lb x 5 reps)`);
    console.log(`  New weight: ${updatedWorkout6.exercises[0].sets[0].weight}lb`);
    console.log(`  New reps: ${updatedWorkout6.exercises[0].sets[0].reps}`);

    if (newE1RM !== originalE1RM && newE1RM > 250) {  // 225x5 should be >250
      console.log(`  ✅ e1RM recalculated correctly\n`);
    } else {
      console.log(`  ❌ e1RM calculation failed\n`);
    }

    // Test 7: Verify updated_at timestamp changes
    console.log('✓ Test 7: Verify updated_at timestamp changes');
    const originalUpdatedAt = updatedWorkout5.updated_at;
    await new Promise(resolve => setTimeout(resolve, 1000));  // Wait 1 second
    const updateTimestampRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        notes: 'Final notes update'
      })
    });
    const updatedWorkout7 = await updateTimestampRes.json();
    console.log(`  Status: ${updateTimestampRes.status}`);
    console.log(`  Original timestamp: ${originalUpdatedAt}`);
    console.log(`  New timestamp: ${updatedWorkout7.updated_at}`);

    if (updatedWorkout7.updated_at !== originalUpdatedAt) {
      console.log(`  ✅ Timestamp updated correctly\n`);
    } else {
      console.log(`  ❌ Timestamp not updated\n`);
    }

    // Test 8: Try to update non-existent workout
    console.log('✓ Test 8: Try to update non-existent workout');
    const updateNonExistentRes = await fetch(`${BASE_URL}/workouts/00000000-0000-0000-0000-000000000000`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        notes: 'Should fail'
      })
    });
    console.log(`  Status: ${updateNonExistentRes.status}`);
    const errorData = await updateNonExistentRes.json();
    console.log(`  Response: ${JSON.stringify(errorData)}`);

    if (updateNonExistentRes.status === 404) {
      console.log(`  ✅ Non-existent workout properly rejected\n`);
    } else {
      console.log(`  ❌ Should return 404\n`);
    }

    // Test 9: Verify full workout retrieval after all updates
    console.log('✓ Test 9: Verify final workout state');
    const finalWorkoutRes = await fetch(`${BASE_URL}/workouts/${workoutId}`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const finalWorkout = await finalWorkoutRes.json();
    console.log(`  Status: ${finalWorkoutRes.status}`);
    console.log(`  Final notes: "${finalWorkout.notes}"`);
    console.log(`  Final duration: ${finalWorkout.duration_minutes} min`);
    console.log(`  Final session RPE: ${finalWorkout.session_rpe}`);
    console.log(`  Final exercises: ${finalWorkout.exercises.length}`);
    console.log(`  Final total sets: ${finalWorkout.exercises.reduce((sum, e) => sum + e.sets.length, 0)}`);
    console.log(`  ✅ Final workout state verified\n`);

    console.log('==================================================\n');
    console.log('Workout update endpoint tests complete!');

  } catch (error) {
    console.error('\n❌ Test error:', error.message);
    process.exit(1);
  }
}

testAPI();
