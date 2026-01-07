# Age-Based Cooldown Modifiers

## Status: ✅ COMPLETED
Started: January 2026
Completed: January 7, 2026

## Goal
Implement age-based modifiers for muscle cooldown times based on research:
- Under 30: 1.0x baseline
- 30-40: 1.15x baseline
- 40-50: 1.3x baseline
- 50+: 1.5x baseline

## Implementation Summary

### Files Modified

1. **`backend/app/services/cooldown_service.py`**
   - Added `get_age_modifier(age: int | None) -> float` function
   - Modified `calculate_cooldowns()` to accept `user_age` parameter
   - Applied age modifier to both primary and secondary muscle cooldown times
   - Added `age_modifier` to response data

2. **`backend/app/schemas/cooldown.py`**
   - Added `age_modifier: float = 1.0` field to `CooldownResponse`

3. **`backend/app/api/analytics.py`**
   - Updated `/cooldowns` endpoint to fetch user profile and pass age to service
   - Added age-based modifier documentation to endpoint docstring

### How It Works

1. When `/api/analytics/cooldowns` is called:
   - Fetches user's `UserProfile` to get their `age` field
   - Passes age to `calculate_cooldowns()`
   - `get_age_modifier()` returns appropriate multiplier
   - Cooldown times are multiplied by the age modifier

2. Example cooldown times with age modifiers:
   ```
   Chest (base 72h):
     Age 25: 72h
     Age 35: 82h (72 × 1.15)
     Age 45: 93h (72 × 1.30)
     Age 55: 108h (72 × 1.50)

   Quads (base 48h):
     Age 25: 48h
     Age 35: 55h
     Age 45: 62h
     Age 55: 72h
   ```

3. If user has no profile or no age set, defaults to 1.0x (baseline)

### API Response

The `/api/analytics/cooldowns` response now includes:
```json
{
  "muscles_cooling": [...],
  "generated_at": "2026-01-07T12:00:00",
  "age_modifier": 1.15
}
```

### Research References

- Recovery time increases with age (PMC sources)
- Young adults (under 30) recover fastest
- Recovery capacity declines approximately 15% per decade after 30

## Testing

Verified:
- `get_age_modifier()` returns correct values for all age ranges
- Cooldown calculations correctly apply the modifier
- All modified files pass Python syntax validation

## Next Steps (Optional Enhancements)

- [ ] Add iOS UI to show the age modifier being applied
- [ ] Allow users to manually adjust their recovery modifier in settings
- [ ] Consider training experience as an additional modifier
