"""
setup_demo.py — One-time setup to unlock CogniMap learning system

Run this ONCE to prepare P01 for testing without research requirements.
"""

import database as db

print("=" * 50)
print("🎓 CogniMap Demo Setup")
print("=" * 50)

# Initialize database
print("\n📦 Initializing database...")
db.initialize_database()
db.seed_participants()
print("✅ Database ready with participants P01-P10")

# Setup P01 for demo
print("\n⚙️  Setting up P01 for demo...")
pid = 1  # P01's ID

# Mark consent as given
db.set_consent_given(pid)
print("✅ Consent recorded")

# Unlock all 6 levels for Layer 1
print("\n🔓 Unlocking all 6 Bloom's levels...")
for level in range(1, 7):
    db.unlock_level(pid, level, layer=1)
    print(f"   Level {level}: Unlocked")

print("\n" + "=" * 50)
print("✅ P01 Ready for CogniMap Demo!")
print("=" * 50)

print("\n📍 Access the demo:")
print("   http://localhost:8501/00_demo")
print("\n📍 Or go directly to Level 1:")
print("   http://localhost:8501/03_level1_remember")
print("\n💡 Login with: P01")
print("=" * 50)
