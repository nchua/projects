#!/bin/bash
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI1Njc0OTM3Zi1kYzgxLTQwODItOTMwYS1hNGRmMDVlNzQzMWIiLCJleHAiOjE3Njk5MjY3NDYsInR5cGUiOiJhY2Nlc3MifQ.H9WK9C4NTvMJWtJ08l5nrh6inkTR91HCDmgrSJz5GBM"

curl -s "https://backend-production-e316.up.railway.app/exercises?limit=5" \
  -H "Authorization: Bearer $TOKEN"
