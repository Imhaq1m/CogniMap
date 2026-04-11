# Module 1: Sequential Progression

## What It Does

Enforces that students complete each Bloom's Taxonomy level in order. Students cannot skip levels and cannot retake completed assessments. Progression is gated by completing each level's core activity — no quizzes.

## How It Works

### State Machine

Each level has three states per student:

| State | Meaning |
|-------|---------|
| `locked` | Level is inaccessible |
| `active` | Level is accessible and in progress |
| `complete` | Level is finished, cannot be re-entered |

**Transitions:**
- `locked` → `active` — triggered when the previous level is completed
- `active` → `complete` — triggered when the current level's activity requirement is met

Level 1 starts as `active`. Levels 2–6 start as `locked`.

### Database

```sql
CREATE TABLE bloom_progress (
    participant_id TEXT DEFAULT 'P01',
    layer INTEGER DEFAULT 1,
    level INTEGER,
    status TEXT DEFAULT 'locked',
    unlocked_at TEXT,
    completed_at TEXT,
    UNIQUE(participant_id, layer, level)
);
```

### Gate Enforcement

Every level-specific API endpoint checks access before processing:

```python
def check_level_access(participant_id, required_level):
    status = database.get_level_status(participant_id, required_level)
    if status != 'active':
        return HTTP 403 Forbidden
```

This prevents URL manipulation (e.g., navigating directly to `/level/2` without completing Level 1).

### Progress Gates

After meeting the level's activity requirement, the level is marked `complete` and the next level is unlocked:

| Level | Name | Activity | Gate |
|-------|------|----------|------|
| 1 | Remember | Define concepts in own words | All concepts AI-validated |
| 2 | Understand | Paraphrase definitions | Similarity 0.85–0.95 for all |
| 3 | Apply | Connect concepts with justifications | 3 edges defended |
| 4 | Analyze | Build complete concept graph | 5 edges defended |
| 5 | Evaluate | Find injected errors | ≥70% detection rate |
| 6 | Create | Generate export artifacts | Utility score ≥70% |

### Progress Tracker

The sidebar displays all six levels with their current status:

```
🧠 Your Learning Journey
✅ Level 1: Remember
▶️ Level 2: Understand ← Current
🔒 Level 3: Apply
🔒 Level 4: Analyze
🔒 Level 5: Evaluate
🔒 Level 6: Create
```
