"""End-to-end integration test for LifePilot."""
import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import httpx
import json

BASE = "http://127.0.0.1:8000"

print("=" * 55)
print("LifePilot End-to-End Integration Test")
print("=" * 55)

# 1. Health check
print("\n[1/4] Health Check...")
try:
    r = httpx.get(f"{BASE}/api/health", timeout=10)
    health = r.json()
    print(f"  Status: {health.get('status')}")
    print(f"  LLM Provider: {health.get('llm_provider')} (available: {health.get('llm_available')})")
    print(f"  Scraping: {health.get('scraping_enabled')}")
    print(f"  Vector DB docs: {health.get('vector_db_documents')}")
    print("  [OK] Health check passed")
except Exception as e:
    print(f"  [FAIL] {e}")

# 2. Frontend
print("\n[2/4] Frontend Check...")
try:
    r = httpx.get(f"{BASE}/", timeout=10)
    has_title = "LifePilot" in r.text
    print(f"  HTTP Status: {r.status_code}")
    print(f"  HTML Length: {len(r.text)} chars")
    print(f"  Contains LifePilot: {has_title}")
    if has_title:
        print("  [OK] Frontend loaded")
    else:
        print("  [WARN] Frontend loaded but missing title")
except Exception as e:
    print(f"  [FAIL] {e}")

# 3. Create profile
print("\n[3/4] Create Test Profile...")
profile_data = {
    "name": "Test User",
    "age": 20,
    "gender": "Male",
    "state": "Karnataka",
    "category": "SC",
    "education_level": "Undergraduate",
    "field_of_study": "Engineering",
    "annual_income": 200000,
    "disability": False,
    "goals": "Complete B.Tech and find a good job"
}
profile_id = None
try:
    r = httpx.post(f"{BASE}/api/profiles", json=profile_data, timeout=10)
    if r.status_code in (200, 201):
        p = r.json()
        profile_id = p.get("id")
        print(f"  Profile created: ID={profile_id}, Name={p.get('name')}")
        print("  [OK] Profile creation passed")
    else:
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        print("  [FAIL] Profile creation failed")
except Exception as e:
    print(f"  [FAIL] {e}")

# 4. API Docs
print("\n[4/4] API Docs Check...")
try:
    r = httpx.get(f"{BASE}/docs", timeout=10)
    has_swagger = "swagger" in r.text.lower() or "openapi" in r.text.lower()
    print(f"  HTTP Status: {r.status_code}")
    print(f"  Has Swagger/OpenAPI: {has_swagger}")
    if has_swagger:
        print("  [OK] API docs accessible")
    else:
        print("  [WARN] Docs loaded but format unclear")
except Exception as e:
    print(f"  [FAIL] {e}")

print("\n" + "=" * 55)
print("Integration test complete!")
print("Server running at: http://127.0.0.1:8000")
print("API Docs at: http://127.0.0.1:8000/docs")
print("=" * 55)
