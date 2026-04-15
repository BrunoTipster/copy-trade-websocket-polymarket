import requests, json
r = requests.get("https://gamma-api.polymarket.com/events",
    params={"slug": "highest-temperature-in-nyc-on-april-16-2026"},
    headers={"User-Agent": "M", "Accept": "application/json"}, timeout=10)
ev = r.json()[0]
print(f"Title: {ev['title']}")
print(f"Markets: {len(ev.get('markets',[]))}\n")
for m in ev.get("markets", [])[:4]:
    q = m.get("question", "")
    toks = m.get("tokens", [])
    op = m.get("outcomePrices", "")
    print(f"Q: {q}")
    print(f"  outcomePrices: {op}")
    for t in toks:
        print(f"  {t.get('outcome')} @ {t.get('price')}")
    print()
