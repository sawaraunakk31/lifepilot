import httpx

BASE = "http://127.0.0.1:8000"

print("=" * 60)
print("Testing New Opportunities API Endpoints")
print("=" * 60)

# 1. Search Schemes
print("\n[1/3] Testing Semantic Search...")
try:
    r = httpx.get(f"{BASE}/api/opportunities/search?q=matric", timeout=15)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        results = r.json()
        print(f"  Found: {len(results)} schemes matching 'matric'")
        for item in results[:2]:
            print(f"    - {item.get('title')}")
        print("  [OK] Search endpoint passed")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Failed: {e}")

# 2. Get Job Openings
print("\n[2/3] Testing Jobs Feed Search...")
try:
    r = httpx.get(f"{BASE}/api/opportunities/jobs?q=engineer", timeout=15)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        results = r.json()
        print(f"  Found: {len(results)} jobs matching 'engineer'")
        for item in results[:2]:
            print(f"    - {item.get('title')} ({item.get('url')[:30]}...)")
        print("  [OK] Jobs search endpoint passed")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Failed: {e}")

# 3. Dynamic Portal Scraper
print("\n[3/3] Testing Portal Scraping & Ingestion...")
try:
    payload = {
        "urls": ["https://weworkremotely.com/remote-jobs.rss"],
        "keywords": ["engineer"]
    }
    r = httpx.post(f"{BASE}/api/opportunities/scrape", json=payload, timeout=25)
    print(f"  Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"  Status: {data.get('status')}")
        print(f"  Scraped count: {data.get('scraped_count')}")
        print(f"  Indexed count: {data.get('indexed_count')}")
        print("  [OK] Scraper API passed")
    else:
        print(f"  Error: {r.text}")
except Exception as e:
    print(f"  Failed: {e}")

print("\n" + "=" * 60)
print("Testing complete!")
print("=" * 60)
