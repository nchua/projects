#!/usr/bin/env node

/**
 * Test script for workout delete endpoint
 * Tests soft delete functionality and verifies deleted workouts don't appear in lists
 */

const BASE_URL = 'http://localhost:8000';

// Test user credentials
const testEmail = `test${Date.now()}@example.com`;
const testPassword = 'TestPass123!';

let authToken = '';
let userId = '';
let workout1Id = '';
let workout2Id = '';
let workout3Id = '';
let exerciseIds = [];

console.log('Testing Workout Delete Endpoint\n');
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
    const exercisesRes = await fetch(`${BASE_URL}/exercises?limit=3`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const exercises = await exercisesRes.json();
    exerciseIds = exercises.map(e => e.id);
    console.log(`  ✅ Test user created, auth token obtained\n`);

    // Create three test workouts
    console.log('✓ Creating three test workouts');

    const workout1Res = await fetch(`${BASE_URL}/workouts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        date: new Date('2024-01-01').toISOString(),
        notes: 'Workout 1',
        exercises: [{
          exercise_id: exerciseIds[0],
          order_index: 0,
          sets: [{ weight: 135, weight_unit: 'lb', reps: 10, set_number: 1 }]
        }]
      })
    });
    const workout1 = await workout1Res.json();
    workout1Id = workout1.id;

    const workout2Res = await fetch(`${BASE_URL}/workouts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        date: new Date('2024-01-02').toISOString(),
        notes: 'Workout 2',
        exercises: [{
          exercise_id: exerciseIds[1],
          order_index: 0,
          sets: [{ weight: 95, weight_unit: 'lb', reps: 8, set_number: 1 }]
        }]
      })
    });
    const workout2 = await workout2Res.json();
    workout2Id = workout2.id;

    const workout3Res = await fetch(`${BASE_URL}/workouts`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        date: new Date('2024-01-03').toISOString(),
        notes: 'Workout 3',
        exercises: [{
          exercise_id: exerciseIds[2],
          order_index: 0,
          sets: [{ weight: 225, weight_unit: 'lb', reps: 5, set_number: 1 }]
        }]
      })
    });
    const workout3 = await workout3Res.json();
    workout3Id = workout3.id;

    console.log(`  Created workout 1: ${workout1Id}`);
    console.log(`  Created workout 2: ${workout2Id}`);
    console.log(`  Created workout 3: ${workout3Id}`);
    console.log(`  ✅ Three workouts created\n`);

    // Test 1: Verify all workouts appear in list
    console.log('✓ Test 1: Verify all workouts appear in list');
    const listBeforeRes = await fetch(`${BASE_URL}/workouts?limit=10`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const listBefore = await listBeforeRes.json();
    console.log(`  Status: ${listBeforeRes.status}`);
    console.log(`  Workouts in list: ${listBefore.length}`);

    if (listBefore.length === 3) {
      console.log(`  ✅ All 3 workouts visible before deletion\n`);
    } else {
      console.log(`  ❌ Expected 3 workouts, found ${listBefore.length}\n`);
    }

    // Test 2: Delete workout 2
    console.log('✓ Test 2: Delete workout 2');
    const deleteRes = await fetch(`${BASE_URL}/workouts/${workout2Id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    console.log(`  Status: ${deleteRes.status}`);

    if (deleteRes.status === 204) {
      console.log(`  ✅ Workout deleted successfully (204 No Content)\n`);
    } else {
      console.log(`  ❌ Expected status 204, got ${deleteRes.status}\n`);
    }

    // Test 3: Verify workout 2 no longer appears in list
    console.log('✓ Test 3: Verify deleted workout no longer in list');
    const listAfterRes = await fetch(`${BASE_URL}/workouts?limit=10`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const listAfter = await listAfterRes.json();
    console.log(`  Status: ${listAfterRes.status}`);
    console.log(`  Workouts in list: ${listAfter.length}`);
    console.log(`  Workout IDs: ${listAfter.map(w => w.notes).join(', ')}`);

    const hasWorkout2 = listAfter.some(w => w.id === workout2Id);
    if (listAfter.length === 2 && !hasWorkout2) {
      console.log(`  ✅ Deleted workout not in list (2 remaining)\n`);
    } else {
      console.log(`  ❌ Deleted workout still appears or count wrong\n`);
    }

    // Test 4: Verify cannot retrieve deleted workout by ID
    console.log('✓ Test 4: Verify cannot retrieve deleted workout by ID');
    const getDeletedRes = await fetch(`${BASE_URL}/workouts/${workout2Id}`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    console.log(`  Status: ${getDeletedRes.status}`);

    if (getDeletedRes.status === 404) {
      const errorData = await getDeletedRes.json();
      console.log(`  Response: ${JSON.stringify(errorData)}`);
      console.log(`  ✅ Deleted workout returns 404\n`);
    } else {
      console.log(`  ❌ Expected 404, got ${getDeletedRes.status}\n`);
    }

    // Test 5: Verify cannot update deleted workout
    console.log('✓ Test 5: Verify cannot update deleted workout');
    const updateDeletedRes = await fetch(`${BASE_URL}/workouts/${workout2Id}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${authToken}`
      },
      body: JSON.stringify({
        notes: 'Should not update'
      })
    });
    console.log(`  Status: ${updateDeletedRes.status}`);

    if (updateDeletedRes.status === 404) {
      const errorData = await updateDeletedRes.json();
      console.log(`  Response: ${JSON.stringify(errorData)}`);
      console.log(`  ✅ Cannot update deleted workout (404)\n`);
    } else {
      console.log(`  ❌ Expected 404, got ${updateDeletedRes.status}\n`);
    }

    // Test 6: Verify cannot delete already deleted workout
    console.log('✓ Test 6: Verify cannot delete already deleted workout');
    const deleteAgainRes = await fetch(`${BASE_URL}/workouts/${workout2Id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    console.log(`  Status: ${deleteAgainRes.status}`);

    if (deleteAgainRes.status === 404) {
      const errorData = await deleteAgainRes.json();
      console.log(`  Response: ${JSON.stringify(errorData)}`);
      console.log(`  ✅ Cannot delete already deleted workout (404)\n`);
    } else {
      console.log(`  ❌ Expected 404, got ${deleteAgainRes.status}\n`);
    }

    // Test 7: Delete another workout
    console.log('✓ Test 7: Delete workout 1');
    const delete1Res = await fetch(`${BASE_URL}/workouts/${workout1Id}`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    console.log(`  Status: ${delete1Res.status}`);
    console.log(`  ✅ Workout 1 deleted\n`);

    // Test 8: Verify only 1 workout remains
    console.log('✓ Test 8: Verify only 1 workout remains');
    const finalListRes = await fetch(`${BASE_URL}/workouts?limit=10`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const finalList = await finalListRes.json();
    console.log(`  Status: ${finalListRes.status}`);
    console.log(`  Workouts in list: ${finalList.length}`);
    console.log(`  Remaining workout: ${finalList[0]?.notes}`);

    if (finalList.length === 1 && finalList[0].id === workout3Id) {
      console.log(`  ✅ Only workout 3 remains\n`);
    } else {
      console.log(`  ❌ Expected only workout 3 to remain\n`);
    }

    // Test 9: Try to delete non-existent workout
    console.log('✓ Test 9: Try to delete non-existent workout');
    const deleteNonExistentRes = await fetch(`${BASE_URL}/workouts/00000000-0000-0000-0000-000000000000`, {
      method: 'DELETE',
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    console.log(`  Status: ${deleteNonExistentRes.status}`);
    const errorData = await deleteNonExistentRes.json();
    console.log(`  Response: ${JSON.stringify(errorData)}`);

    if (deleteNonExistentRes.status === 404) {
      console.log(`  ✅ Non-existent workout properly rejected\n`);
    } else {
      console.log(`  ❌ Expected 404\n`);
    }

    // Test 10: Verify remaining workout still accessible
    console.log('✓ Test 10: Verify remaining workout still accessible');
    const getWorkout3Res = await fetch(`${BASE_URL}/workouts/${workout3Id}`, {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    const workout3Data = await getWorkout3Res.json();
    console.log(`  Status: ${getWorkout3Res.status}`);
    console.log(`  Workout notes: "${workout3Data.notes}"`);
    console.log(`  Exercises: ${workout3Data.exercises.length}`);

    if (getWorkout3Res.status === 200 && workout3Data.notes === 'Workout 3') {
      console.log(`  ✅ Non-deleted workout still accessible\n`);
    } else {
      console.log(`  ❌ Failed to retrieve non-deleted workout\n`);
    }

    console.log('==================================================\n');
    console.log('Workout delete endpoint tests complete!');

  } catch (error) {
    console.error('\n❌ Test error:', error.message);
    process.exit(1);
  }
}

testAPI();
