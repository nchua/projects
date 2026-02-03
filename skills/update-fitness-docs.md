# Update Fitness App Documentation

A weekly process for keeping mockups and documentation in sync with the iOS app.

## Quick Start
Run this skill when you've made significant iOS changes and want to update docs.

## Weekly Checklist

### 1. Identify What Changed
- [ ] Check recent git commits: `git log --oneline -20`
- [ ] Review iOS Views/ for UI changes
- [ ] Check for new features in HomeView, StatsView, etc.
- [ ] Note any tab structure changes

### 2. Compare App vs Mockups
- [ ] Tab bar matches? (Home, Quests, Dungeons, Friends, Stats)
- [ ] Home screen sections match current HomeView.swift?
- [ ] Stats page shows all current exercises?
- [ ] New features have mockup pages?

### 3. Update Website Mockups
Location: `personal-website/site/projects/fitness-app/`

For each changed screen:
1. Read the current iOS View file
2. Update the corresponding mockup HTML
3. Maintain EdgeFlow design consistency
4. Test in browser

### 4. Update README if Needed
Location: `fitness-app/README.md`

- [ ] Feature list current?
- [ ] API endpoints documented?
- [ ] Tech stack accurate?

### 5. Sync to GitHub Mirror
```bash
cp -r personal-website/site/projects/fitness-app/* personal-website/github-repo/projects/fitness-app/
```

### 6. Deploy
```bash
cd personal-website/site && git add . && git commit -m "Update fitness app mockups" && git push
```

## Key Files Reference

| iOS View | Mockup File |
|----------|-------------|
| HomeView.swift | home.html |
| QuestsView.swift | quests.html |
| DungeonsView.swift | dungeons.html |
| FriendsView.swift | friends.html |
| StatsView.swift | stats.html |
| LogView.swift | log.html |
| MissionCard.swift | coaching.html |
| GoalSetupView.swift | goal-setup.html |

## Design Tokens
- Background: #050508
- Card: #0f1018
- Cyan: #00D4FF
- Green: #00FF88
- Gold: #FFD700

## Tab Bar Structure (Current)
```
Home | Quests | Dungeons | Friends | Stats
```

## Recent Changes (Feb 2026)

### Coaching & Goals Feature
- MissionCard.swift shows weekly missions on home screen
- GoalSetupView.swift has 4-step goal creation flow
- Three mission states: empty, ready (offered), active

### Stats Page Expansion
- Now supports 20+ exercises with percentile rankings
- Additional exercises beyond Big Three show rank badges and trends

## Common Updates

### Adding a New Tab
1. Update tab bar HTML in ALL mockup files
2. Create new mockup page for the tab content
3. Add card to index.html
4. Update this checklist

### Adding a New Home Section
1. Update home.html with new section HTML
2. Match styling from HomeView.swift
3. Verify scroll behavior works

### Updating Stats
1. Check backend/app/api/analytics.py for supported exercises
2. Update stats.html "Additional Exercises" section
3. Add rank badge styling if needed
