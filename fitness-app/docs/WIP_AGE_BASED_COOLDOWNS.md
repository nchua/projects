# WIP: Age-Based Cooldown Modifiers

## Status: IN PROGRESS
Started: January 2026

## Goal
Implement age-based modifiers for muscle cooldown times based on research:
- Under 30: 1.0x baseline
- 30-40: 1.15x baseline
- 40-50: 1.3x baseline
- 50+: 1.5x baseline

## Progress

### ✅ Completed
1. **Documentation** - Added to Future Improvements in `COOLDOWN_FEATURE.md`
2. **Research** - Verified age affects recovery (PMC sources linked)
3. **Found age field** - `UserProfile.age` exists in `backend/app/models/user.py:60`

### 🔄 In Progress
1. **Update cooldown service** - Need to modify `calculate_cooldowns()` function

### ⏳ TODO
1. Update `cooldown_service.py` to:
   - Accept user's age as parameter (or fetch from profile)
   - Add `get_age_modifier(age: int)` function
   - Apply modifier to `COOLDOWN_TIMES` values
2. Update `analytics.py` endpoint to pass age to cooldown service
3. Test the implementation
4. Commit and deploy

## Files to Modify

### 1. `backend/app/services/cooldown_service.py`
Add age modifier function:
```python
def get_age_modifier(age: int | None) -> float:
    """Get cooldown multiplier based on user age."""
    if age is None:
        return 1.0  # Default if age not set
    if age < 30:
        return 1.0
    elif age < 40:
        return 1.15
    elif age < 50:
        return 1.3
    else:
        return 1.5
```

Modify `calculate_cooldowns()` to:
- Fetch user profile to get age
- Apply modifier to cooldown times

### 2. `backend/app/api/analytics.py`
The endpoint already has access to `current_user` and `db`, so we can fetch the profile there and pass age to the service.

## Current Code Reference

### User Profile Model (`backend/app/models/user.py:52-73`)
```python
class UserProfile(Base):
    __tablename__ = "user_profiles"
    id = Column(String, primary_key=True, ...)
    user_id = Column(String, ForeignKey("users.id"), ...)
    age = Column(Integer, nullable=True)  # <-- This field
    # ... other fields
```

### Cooldown Times (`backend/app/services/cooldown_service.py:24-32`)
```python
COOLDOWN_TIMES = {
    "chest": 72,
    "quads": 48,
    "hamstrings": 72,
    "biceps": 36,
    "triceps": 36,
    "shoulders": 48,
}
```

### Analytics Endpoint (`backend/app/api/analytics.py:722-746`)
```python
@router.get("/cooldowns", response_model=CooldownResponse)
async def get_cooldown_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cooldown_data = calculate_cooldowns(db, current_user.id)
    return CooldownResponse(**cooldown_data)
```

## Next Steps
1. Read the full `cooldown_service.py` to understand `calculate_cooldowns()` function
2. Add `get_age_modifier()` function
3. Modify `calculate_cooldowns()` to fetch user profile and apply modifier
4. Test locally
5. Commit and deploy
