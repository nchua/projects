#!/bin/bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1Njc0OTM3Zi1kYzgxLTQwODItOTMwYS1hNGRmMDVlNzQzMWIiLCJleHAiOjE3Njk5MjY3NDYsInR5cGUiOiJhY2Nlc3MifQ.H9WK9C4NTvMJWtJ08l5nrh6inkTR91HCDmgrSJz5GBM"

curl -s -X POST "https://backend-production-e316.up.railway.app/workouts" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Workout",
    "started_at": "2026-01-02T10:00:00",
    "completed_at": "2026-01-02T11:00:00",
    "duration_seconds": 3600,
    "exercises": [
      {
        "exercise_id": "squat",
        "order_index": 0,
        "sets": [
          {"set_number": 1, "reps": 5, "weight": 225, "is_warmup": false}
        ]
      }
    ]
  }'
