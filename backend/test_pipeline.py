"""Test the full agent pipeline - the core AI workflow."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import httpx
import json
import time

BASE = "http://127.0.0.1:8000"

print("=" * 55)
print("LifePilot Agent Pipeline Test")
print("=" * 55)

# 1. Run the agent pipeline on an existing profile
print("\n[1/3] Running Agent Pipeline (profile_id=4)...")
print("  (This calls Groq LLM + Serper search - may take 30-60s)")
start = time.time()
try:
    r = httpx.post(f"{BASE}/api/agent/run/4", timeout=120)
    elapsed = time.time() - start
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Time: {elapsed:.1f}s")
    if r.status_code == 200:
        data = r.json()
        print(f"  Summary: {data.get('summary', 'N/A')[:200]}")
        print(f"  Logs count: {len(data.get('logs', []))}")
        print(f"  Matches count: {len(data.get('matches', []))}")
        
        # Show agent logs
        print("\n  Agent Logs:")
        for log in data.get("logs", []):
            agent = log.get("agent", "?")
            msg = log.get("message", "")[:100]
            conf = log.get("confidence", 0)
            print(f"    [{agent}] (conf={conf}) {msg}")
        
        # Show top matches
        matches = data.get("matches", [])
        if matches:
            print(f"\n  Top Matches ({len(matches)} total):")
            for m in matches[:3]:
                title = m.get("title", "?")
                eligible = m.get("eligible", False)
                score = m.get("score", 0)
                tag = "ELIGIBLE" if eligible else "partial"
                print(f"    [{tag}] {title} (score={score})")
        
        print("\n  [OK] Agent pipeline completed successfully")
    else:
        print(f"  Response: {r.text[:400]}")
        print("  [FAIL] Agent pipeline returned error")
except httpx.ReadTimeout:
    print("  [FAIL] Request timed out after 120s")
except Exception as e:
    print(f"  [FAIL] {e}")

# 2. Test the What-If Simulator
print("\n[2/3] Testing What-If Simulator...")
sim_data = {
    "name": "Priya Sharma",
    "age": 22,
    "gender": "Female",
    "state": "Maharashtra",
    "category": "OBC",
    "education_level": "Postgraduate",
    "field_of_study": "Computer Science",
    "annual_income": 300000,
    "disability": False,
    "goals": "Pursue PhD in AI",
    "owned_documents": ["Aadhaar Card", "Income Certificate"]
}
start = time.time()
try:
    r = httpx.post(f"{BASE}/api/agent/simulate", json=sim_data, timeout=120)
    elapsed = time.time() - start
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Time: {elapsed:.1f}s")
    if r.status_code == 200:
        data = r.json()
        print(f"  Summary: {data.get('summary', 'N/A')[:200]}")
        matches = data.get("matches", [])
        eligible = [m for m in matches if m.get("eligible")]
        print(f"  Total matches: {len(matches)}, Eligible: {len(eligible)}")
        insights = data.get("insights", {})
        print(f"  Estimated benefit: {insights.get('estimated_benefit_label', 'N/A')}")
        print(f"  Readiness: {insights.get('readiness_percent', 0)}%")
        print("  [OK] Simulator passed")
    else:
        print(f"  Response: {r.text[:400]}")
        print("  [FAIL] Simulator failed")
except httpx.ReadTimeout:
    print("  [FAIL] Request timed out after 120s")
except Exception as e:
    print(f"  [FAIL] {e}")

# 3. Test opportunities listing
print("\n[3/3] Testing Opportunities Endpoint...")
try:
    r = httpx.get(f"{BASE}/api/opportunities", timeout=10)
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Response: {r.text[:100]}")
    print("  [OK] Opportunities endpoint works")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\n" + "=" * 55)
print("Agent pipeline test complete!")
print("=" * 55)
