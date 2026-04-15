"""
🏆 TOP 2 MELHORES ENTRADAS — Polymarket Weather
Temp atual + ECMWF + Open-Meteo → compara com mercado → recomenda.
"""
import requests, json, re, math
from datetime import date
from statistics import median

H = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
DS = "april-16-2026"

CIDADES = [
    ("NYC",       f"highest-temperature-in-nyc-on-{DS}",       40.78, -73.88),
    ("Miami",     f"highest-temperature-in-miami-on-{DS}",     25.80, -80.28),
    ("Chicago",   f"highest-temperature-in-chicago-on-{DS}",   41.98, -87.91),
    ("Dallas",    f"highest-temperature-in-dallas-on-{DS}",    32.78, -96.80),
    ("LA",        f"highest-temperature-in-los-angeles-on-{DS}", 33.94, -118.41),
    ("Atlanta",   f"highest-temperature-in-atlanta-on-{DS}",   33.75, -84.39),
    ("London",    f"highest-temperature-in-london-on-{DS}",    51.51, 0.05),
    ("Paris",     f"highest-temperature-in-paris-on-{DS}",     49.01, 2.55),
    ("Tokyo",     f"highest-temperature-in-tokyo-on-{DS}",     35.55, 139.78),
    ("Seoul",     f"highest-temperature-in-seoul-on-{DS}",     37.46, 126.44),
    ("Toronto",   f"highest-temperature-in-toronto-on-{DS}",   43.65, -79.38),
    ("São Paulo", f"highest-temperature-in-sao-paulo-on-{DS}", -23.43, -46.47),
    ("Amsterdam", f"highest-temperature-in-amsterdam-on-{DS}", 52.31, 4.76),
    ("Shanghai",  f"highest-temperature-in-shanghai-on-{DS}",  31.14, 121.80),
]

def get_weather(lat, lon):
    t_agora = t_prev = t_ecmwf = None; hora = 0
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast",
            params={"latitude":lat,"longitude":lon,"current":"temperature_2m",
                    "daily":"temperature_2m_max","timezone":"auto","forecast_days":3}, timeout=8)
        d = r.json()
        t_agora = d.get("current",{}).get("temperature_2m")
        try: hora = int(d.get("current",{}).get("time","").split("T")[1].split(":")[0])
        except: pass
        datas = d.get("daily",{}).get("time",[])
        maxs = d.get("daily",{}).get("temperature_2m_max",[])
        ds = "2026-04-16"
        if ds in datas: t_prev = maxs[datas.index(ds)]
    except: pass
    try:
        r2 = requests.get("https://api.open-meteo.com/v1/ecmwf",
            params={"latitude":lat,"longitude":lon,"daily":"temperature_2m_max",
                    "timezone":"auto","forecast_days":3}, timeout=8)
        d2 = r2.json()
        datas2 = d2.get("daily",{}).get("time",[])
        maxs2 = d2.get("daily",{}).get("temperature_2m_max",[])
        if "2026-04-16" in datas2: t_ecmwf = maxs2[datas2.index("2026-04-16")]
    except: pass
    return t_agora, t_prev, t_ecmwf, hora

def f2c(f): return round((f - 32) * 5 / 9, 1)

def parse_faixa(question):
    """Extrai faixa de temperatura da question. Retorna (min_c, max_c, label)."""
    q = question.lower()
    # "between 82-83°F" ou "between 82-83°f"
    m = re.search(r'between\s+(\d+)-(\d+)\s*°?\s*f', q)
    if m:
        f1, f2 = float(m.group(1)), float(m.group(2))
        return f2c(f1), f2c(f2), f"{int(f1)}-{int(f2)}°F ({f2c(f1)}-{f2c(f2)}°C)"
    # "77°F or below"
    m = re.search(r'(\d+)\s*°?\s*f\s*or\s*below', q)
    if m:
        f1 = float(m.group(1))
        return -99, f2c(f1), f"≤{int(f1)}°F (≤{f2c(f1)}°C)"
    # "82°F or higher"
    m = re.search(r'(\d+)\s*°?\s*f\s*or\s*(higher|above)', q)
    if m:
        f1 = float(m.group(1))
        return f2c(f1), 99, f"≥{int(f1)}°F (≥{f2c(f1)}°C)"
    # Celsius: "22°C"
    m = re.search(r'be\s+(\d+)\s*°?\s*c\b', q)
    if m:
        c = float(m.group(1))
        return c, c, f"{int(c)}°C"
    # "between 22-23°C"
    m = re.search(r'between\s+(\d+)-(\d+)\s*°?\s*c', q)
    if m:
        return float(m.group(1)), float(m.group(2)), f"{m.group(1)}-{m.group(2)}°C"
    # "22°C or higher"
    m = re.search(r'(\d+)\s*°?\s*c\s*or\s*(higher|above)', q)
    if m:
        return float(m.group(1)), 99, f"≥{m.group(1)}°C"
    # "22°C or below"
    m = re.search(r'(\d+)\s*°?\s*c\s*or\s*below', q)
    if m:
        return -99, float(m.group(1)), f"≤{m.group(1)}°C"
    return None, None, question

def prob_normal(mu, sigma, fmin, fmax):
    sigma = max(sigma, 0.8)
    def cdf(x): return 0.5 * (1 + math.erf((x - mu) / (sigma * 1.4142)))
    return max(0.0, min(1.0, cdf(fmax + 0.5) - cdf(fmin - 0.5)))

print("=" * 60)
print(f"  🌡️ SCAN POLYMARKET WEATHER — 16/04/2026")
print("=" * 60)

todos = []

for cidade, slug, lat, lon in CIDADES:
    try:
        r = requests.get("https://gamma-api.polymarket.com/events",
            params={"slug": slug}, headers=H, timeout=10)
        events = r.json()
        if not events: continue
        ev = events[0]
        markets = ev.get("markets", [])
        if not markets: continue

        t_agora, t_prev, t_ecmwf, hora = get_weather(lat, lon)
        fontes = [x for x in [t_prev, t_ecmwf] if x]
        prev_central = round(median(fontes), 1) if fontes else None
        sigma = abs(t_prev - t_ecmwf) / 2 if t_prev and t_ecmwf else 1.5

        opcoes = []
        for mkt in markets:
            q = mkt.get("question", "")
            op = mkt.get("outcomePrices", "")
            try:
                prices = json.loads(op) if isinstance(op, str) else op
                yes_price = float(prices[0])
            except:
                yes_price = 0
            if yes_price < 0.005: continue

            fmin, fmax, label = parse_faixa(q)
            if fmin is None: continue

            # Calcula probabilidade real
            if prev_central:
                prob_real = round(prob_normal(prev_central, sigma, fmin, fmax) * 100, 1)
            else:
                prob_real = 0

            edge = round(prob_real - yes_price * 100, 1)

            opcoes.append({
                "label": label, "yes_pct": round(yes_price*100,1),
                "prob_real": prob_real, "edge": edge,
                "fmin": fmin, "fmax": fmax,
            })

        opcoes.sort(key=lambda x: x["edge"], reverse=True)
        best_edge = opcoes[0]["edge"] if opcoes else 0

        todos.append({
            "cidade": cidade, "slug": slug,
            "t_agora": round(t_agora,1) if t_agora else None,
            "t_prev": round(t_prev,1) if t_prev else None,
            "t_ecmwf": round(t_ecmwf,1) if t_ecmwf else None,
            "prev_central": prev_central, "sigma": round(sigma,1),
            "hora": hora, "opcoes": opcoes, "best_edge": best_edge,
        })
        print(f"  ✅ {cidade:<12} | Agora:{t_agora}°C | ECMWF:{t_ecmwf}°C | OM:{t_prev}°C | Edge:{best_edge:+.0f}%")
    except Exception as e:
        print(f"  ❌ {cidade}: {e}")

# Ordena por melhor edge
todos.sort(key=lambda x: x["best_edge"], reverse=True)

print(f"\n{'='*60}")
print(f"  🏆 TOP 2 MELHORES ENTRADAS AGORA")
print(f"{'='*60}")

for i, o in enumerate(todos[:2], 1):
    t_f = round(o["t_agora"] * 9/5 + 32) if o["t_agora"] else "?"
    print(f"\n{'━'*55}")
    print(f"  #{i} {o['cidade']} — 16/04/2026")
    print(f"{'━'*55}")
    print(f"  🌡️ Temp agora: {o['t_agora']}°C ({t_f}°F) | Hora local: {o['hora']}h")
    if o["t_ecmwf"]: print(f"  🇪🇺 ECMWF máxima: {o['t_ecmwf']}°C")
    if o["t_prev"]:  print(f"  🌐 Open-Meteo máxima: {o['t_prev']}°C")
    if o["prev_central"]: print(f"  📊 Central: {o['prev_central']}°C ±{o['sigma']}°C")

    print(f"\n  📊 Opções (Mercado vs Real):")
    for oc in o["opcoes"][:6]:
        if oc["edge"] >= 8:    seta = "🔥"
        elif oc["edge"] > 0:   seta = "⬆️"
        elif oc["edge"] > -5:  seta = "➡️"
        else:                  seta = "⬇️"
        print(f"  {seta} {oc['label']:<25} Mkt:{oc['yes_pct']:>5}% Real:{oc['prob_real']:>5}% Edge:{oc['edge']:+.0f}%")

    best = o["opcoes"][0]
    print(f"\n  ⚡ MELHOR: {best['label']} — edge +{best['edge']}%")

    if o["hora"] >= 16:
        print(f"  💡 Dia acabando → temp atual ({o['t_agora']}°C) é a máxima")
    elif o["hora"] >= 14:
        print(f"  💡 Pico de calor → pode subir +0-1°C")
    elif o["hora"] >= 11:
        print(f"  💡 Ainda subindo → pode subir +1-3°C")
    else:
        print(f"  💡 Manhã → aguardar pico (após 14h local)")

    print(f"  🔗 https://polymarket.com/event/{o['slug']}")
