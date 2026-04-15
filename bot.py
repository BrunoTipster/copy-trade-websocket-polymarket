"""
╔══════════════════════════════════════════════════════════════╗
║   POLYMARKET WEATHER EDGE BOT v2.0                          ║
║   Usa as MESMAS fontes que o Polymarket usa para resolver   ║
║   cada mercado → máxima precisão possível                   ║
╚══════════════════════════════════════════════════════════════╝

FONTES EXATAS POR CIDADE (pesquisadas nos mercados reais):
  Hong Kong  → HKO (Hong Kong Observatory) climat.htm
  Seoul      → Wunderground RKSI (Incheon Airport)
  São Paulo  → Wunderground SBGR (Guarulhos Airport)
  Tel Aviv   → Wunderground LLBG (Ben Gurion Airport)
  Taipei     → Wunderground RCSS (Songshan Airport)
  Karachi    → Wunderground OPKC (Karachi Airport)
  Lucknow    → Wunderground VILK (Lucknow Airport)
  Shanghai   → Wunderground ZSPD (Pudong Airport)
  NYC        → Wunderground KLGA (LaGuardia Airport)
  London     → Wunderground EGLC (London City Airport)
  + 15 outras cidades com estações mapeadas

Instalação:
  pip install requests beautifulsoup4

Uso:
  python weather_edge_bot.py
"""

import requests
import time
import json
import re
import math
from datetime import datetime, date, timedelta
from statistics import median

# ═══════════════════════════════════════════
#  CONFIGURAÇÕES
# ═══════════════════════════════════════════

TELEGRAM_TOKEN   = "8744601987:AAFVTdhf2qyDE-OgooIesuHMd9PmhBGSIqo"
TELEGRAM_CHAT_ID = "-1003910452966"

MIN_EDGE  = 8.0   # % mínimo de edge para alertar
INTERVALO = 300   # segundos entre varreduras (5 min)

HEADERS_WEB = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json",
}

# ═══════════════════════════════════════════
#  MAPA CIDADE → FONTE EXATA DO POLYMARKET
# ═══════════════════════════════════════════

CIDADES = {
    # ── ÁSIA ──
    "hong kong": {
        "source": "hko",
        "hko_api": "https://data.weather.gov.hk/weatherAPI/opendata/climate.php",
        "lat": 22.28, "lon": 114.17,
        "precision": "decimal",  # 9.1°C
        "unidade": "C",
    },
    "seoul": {
        "source": "wunderground",
        "station": "RKSI",
        "wu_url": "https://www.wunderground.com/history/daily/kr/incheon/RKSI",
        "lat": 37.46, "lon": 126.44,
        "precision": "integer",
        "unidade": "C",
    },
    "taipei": {
        "source": "wunderground",
        "station": "RCSS",
        "wu_url": "https://www.wunderground.com/history/daily/tw/taipei/RCSS",
        "lat": 25.07, "lon": 121.55,
        "precision": "integer",
        "unidade": "C",
    },
    "karachi": {
        "source": "wunderground",
        "station": "OPKC",
        "wu_url": "https://www.wunderground.com/history/daily/pk/karachi/OPKC",
        "lat": 24.90, "lon": 67.16,
        "precision": "integer",
        "unidade": "C",
    },
    "lucknow": {
        "source": "wunderground",
        "station": "VILK",
        "wu_url": "https://www.wunderground.com/history/daily/in/lucknow/VILK",
        "lat": 26.76, "lon": 80.88,
        "precision": "integer",
        "unidade": "C",
    },
    "shanghai": {
        "source": "wunderground",
        "station": "ZSPD",
        "wu_url": "https://www.wunderground.com/history/daily/cn/shanghai/ZSPD",
        "lat": 31.14, "lon": 121.80,
        "precision": "integer",
        "unidade": "C",
    },
    "shenzhen": {
        "source": "wunderground",
        "station": "ZGSZ",
        "wu_url": "https://www.wunderground.com/history/daily/cn/shenzhen/ZGSZ",
        "lat": 22.64, "lon": 113.81,
        "precision": "integer",
        "unidade": "C",
    },
    "beijing": {
        "source": "wunderground",
        "station": "ZBAA",
        "wu_url": "https://www.wunderground.com/history/daily/cn/beijing/ZBAA",
        "lat": 40.08, "lon": 116.58,
        "precision": "integer",
        "unidade": "C",
    },
    "tokyo": {
        "source": "wunderground",
        "station": "RJTT",
        "wu_url": "https://www.wunderground.com/history/daily/jp/tokyo/RJTT",
        "lat": 35.55, "lon": 139.78,
        "precision": "integer",
        "unidade": "C",
    },
    "singapore": {
        "source": "wunderground",
        "station": "WSSS",
        "wu_url": "https://www.wunderground.com/history/daily/sg/singapore/WSSS",
        "lat": 1.36, "lon": 103.99,
        "precision": "integer",
        "unidade": "C",
    },
    "dubai": {
        "source": "wunderground",
        "station": "OMDB",
        "wu_url": "https://www.wunderground.com/history/daily/ae/dubai/OMDB",
        "lat": 25.25, "lon": 55.36,
        "precision": "integer",
        "unidade": "C",
    },
    "mumbai": {
        "source": "wunderground",
        "station": "VABB",
        "wu_url": "https://www.wunderground.com/history/daily/in/mumbai/VABB",
        "lat": 19.09, "lon": 72.87,
        "precision": "integer",
        "unidade": "C",
    },
    "delhi": {
        "source": "wunderground",
        "station": "VIDP",
        "wu_url": "https://www.wunderground.com/history/daily/in/delhi/VIDP",
        "lat": 28.56, "lon": 77.10,
        "precision": "integer",
        "unidade": "C",
    },
    "tel aviv": {
        "source": "wunderground",
        "station": "LLBG",
        "wu_url": "https://www.wunderground.com/history/daily/il/tel-aviv/LLBG",
        "lat": 32.01, "lon": 34.89,
        "precision": "integer",
        "unidade": "C",
    },
    # ── AMÉRICAS ──
    "sao paulo": {
        "source": "wunderground",
        "station": "SBGR",
        "wu_url": "https://www.wunderground.com/history/daily/br/guarulhos/SBGR",
        "lat": -23.43, "lon": -46.47,
        "precision": "integer",
        "unidade": "C",
    },
    "são paulo": {
        "source": "wunderground",
        "station": "SBGR",
        "wu_url": "https://www.wunderground.com/history/daily/br/guarulhos/SBGR",
        "lat": -23.43, "lon": -46.47,
        "precision": "integer",
        "unidade": "C",
    },
    "new york": {
        "source": "wunderground",
        "station": "KLGA",
        "wu_url": "https://www.wunderground.com/history/daily/us/ny/new-york-city/KLGA",
        "lat": 40.78, "lon": -73.88,
        "precision": "integer",
        "unidade": "F",  # NYC usa Fahrenheit
    },
    "nyc": {
        "source": "wunderground",
        "station": "KLGA",
        "wu_url": "https://www.wunderground.com/history/daily/us/ny/new-york-city/KLGA",
        "lat": 40.78, "lon": -73.88,
        "precision": "integer",
        "unidade": "F",
    },
    "seattle": {
        "source": "wunderground",
        "station": "KSEA",
        "wu_url": "https://www.wunderground.com/history/daily/us/wa/seattle/KSEA",
        "lat": 47.45, "lon": -122.31,
        "precision": "integer",
        "unidade": "F",
    },
    "chicago": {
        "source": "wunderground",
        "station": "KORD",
        "wu_url": "https://www.wunderground.com/history/daily/us/il/chicago/KORD",
        "lat": 41.98, "lon": -87.91,
        "precision": "integer",
        "unidade": "F",
    },
    "miami": {
        "source": "wunderground",
        "station": "KMIA",
        "wu_url": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        "lat": 25.80, "lon": -80.28,
        "precision": "integer",
        "unidade": "F",
    },
    "los angeles": {
        "source": "wunderground",
        "station": "KLAX",
        "wu_url": "https://www.wunderground.com/history/daily/us/ca/los-angeles/KLAX",
        "lat": 33.94, "lon": -118.41,
        "precision": "integer",
        "unidade": "F",
    },
    # ── EUROPA ──
    "london": {
        "source": "wunderground",
        "station": "EGLC",
        "wu_url": "https://www.wunderground.com/history/daily/gb/london/EGLC",
        "lat": 51.51, "lon": 0.05,
        "precision": "integer",
        "unidade": "C",
    },
    "paris": {
        "source": "wunderground",
        "station": "LFPG",
        "wu_url": "https://www.wunderground.com/history/daily/fr/roissy-en-france/LFPG",
        "lat": 49.01, "lon": 2.55,
        "precision": "integer",
        "unidade": "C",
    },
    "berlin": {
        "source": "wunderground",
        "station": "EDDB",
        "wu_url": "https://www.wunderground.com/history/daily/de/berlin/EDDB",
        "lat": 52.37, "lon": 13.52,
        "precision": "integer",
        "unidade": "C",
    },
    "amsterdam": {
        "source": "wunderground",
        "station": "EHAM",
        "wu_url": "https://www.wunderground.com/history/daily/nl/amsterdam/EHAM",
        "lat": 52.31, "lon": 4.76,
        "precision": "integer",
        "unidade": "C",
    },
    "madrid": {
        "source": "wunderground",
        "station": "LEMD",
        "wu_url": "https://www.wunderground.com/history/daily/es/madrid/LEMD",
        "lat": 40.47, "lon": -3.56,
        "precision": "integer",
        "unidade": "C",
    },
    "moscow": {
        "source": "wunderground",
        "station": "UUEE",
        "wu_url": "https://www.wunderground.com/history/daily/ru/moscow/UUEE",
        "lat": 55.97, "lon": 37.41,
        "precision": "integer",
        "unidade": "C",
    },
}

# Cache global
_cache_wu    = {}   # "station|data" → temp_celsius
_cache_hko   = {}   # "data" → temp_celsius
_cache_om    = {}   # "lat|lon|data" → temp_celsius
alertas_env  = set()

# ═══════════════════════════════════════════
#  TRACKING WIN/LOSS — salva em trades.json
# ═══════════════════════════════════════════

TRADES_FILE = "trades.json"

def carregar_trades():
    """Carrega trades pendentes do JSON."""
    try:
        if os.path.exists(TRADES_FILE):
            with open(TRADES_FILE, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {"pendentes": [], "historico": [], "stats": {"wins": 0, "losses": 0, "lucro_total": 0}}

def salvar_trades(data):
    """Salva trades no JSON."""
    try:
        with open(TRADES_FILE, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[ERRO] salvar trades: {e}")

def registrar_entrada(cidade, data_str, outcome, edge, prob_real, prob_mkt, price, slug):
    """Registra uma entrada recomendada como pendente."""
    db = carregar_trades()
    # Evita duplicata
    for p in db["pendentes"]:
        if p["cidade"] == cidade and p["data"] == data_str and p["outcome"] == outcome:
            return
    db["pendentes"].append({
        "cidade": cidade,
        "data": data_str,
        "outcome": outcome,
        "edge": edge,
        "prob_real": prob_real,
        "prob_mkt": prob_mkt,
        "price": price,
        "slug": slug,
        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "status": "PENDENTE",
    })
    salvar_trades(db)
    print(f"[TRADE] Registrado: {cidade} {data_str} → {outcome} (edge +{edge}%)")

def verificar_resultados():
    """
    Verifica mercados resolvidos e atualiza WIN/LOSS.
    Busca na Gamma API se o mercado já fechou.
    """
    db = carregar_trades()
    if not db["pendentes"]:
        return

    pendentes_novos = []
    algum_resolvido = False

    for trade in db["pendentes"]:
        slug = trade.get("slug", "")
        if not slug:
            pendentes_novos.append(trade)
            continue

        try:
            r = requests.get("https://gamma-api.polymarket.com/events",
                params={"slug": slug}, headers=HEADERS_API, timeout=10)
            events = r.json()
            if not events:
                pendentes_novos.append(trade)
                continue

            ev = events[0]
            resolvido = False
            ganhou = False

            for mkt in ev.get("markets", []):
                q = (mkt.get("question") or "").lower()
                outcome_trade = trade["outcome"].lower()

                # Verifica se esse sub-market corresponde ao outcome
                if outcome_trade not in q:
                    continue

                closed = mkt.get("closed", False)
                resolution = mkt.get("resolution", "")

                if closed or resolution:
                    resolvido = True
                    # resolution = "Yes" ou "No"
                    if str(resolution).lower() == "yes":
                        ganhou = True
                    break

            if resolvido:
                algum_resolvido = True
                resultado = "WIN" if ganhou else "LOSS"
                lucro = round((1 - trade["price"]) * 100, 1) if ganhou else round(-trade["price"] * 100, 1)

                trade["status"] = resultado
                trade["lucro_pct"] = lucro
                trade["resolvido_em"] = datetime.now().strftime("%d/%m/%Y %H:%M")
                db["historico"].append(trade)

                if ganhou:
                    db["stats"]["wins"] += 1
                    db["stats"]["lucro_total"] += lucro
                else:
                    db["stats"]["losses"] += 1
                    db["stats"]["lucro_total"] += lucro

                # Envia no Telegram
                w = db["stats"]["wins"]
                l = db["stats"]["losses"]
                total = w + l
                taxa = round(w / total * 100, 1) if total > 0 else 0

                if ganhou:
                    msg = (
                        f"🟢🟢🟢 <b>WIN!</b> 🟢🟢🟢\n\n"
                        f"📌 {trade['cidade']} ({trade['data']})\n"
                        f"🎯 {trade['outcome']}\n"
                        f"⚡ Edge era: +{trade['edge']}%\n"
                        f"💰 Retorno: <b>+{lucro}%</b>\n\n"
                        f"📊 Total: {w}W / {l}L ({taxa}% acerto)"
                    )
                else:
                    msg = (
                        f"🔴🔴🔴 <b>LOSS</b> 🔴🔴🔴\n\n"
                        f"📌 {trade['cidade']} ({trade['data']})\n"
                        f"🎯 {trade['outcome']}\n"
                        f"⚡ Edge era: +{trade['edge']}%\n"
                        f"💸 Perda: <b>{lucro}%</b>\n\n"
                        f"📊 Total: {w}W / {l}L ({taxa}% acerto)"
                    )
                enviar_telegram(msg)
                print(f"[{resultado}] {trade['cidade']} {trade['outcome']} → {lucro}%")
            else:
                pendentes_novos.append(trade)

        except Exception as e:
            print(f"[ERRO] verificar {trade['cidade']}: {e}")
            pendentes_novos.append(trade)

        time.sleep(0.2)

    db["pendentes"] = pendentes_novos
    salvar_trades(db)

    if algum_resolvido:
        w = db["stats"]["wins"]
        l = db["stats"]["losses"]
        print(f"[STATS] W:{w} L:{l} Lucro:{db['stats']['lucro_total']:.1f}%")


# ═══════════════════════════════════════════
#  TELEGRAM
# ═══════════════════════════════════════════

def enviar_telegram(msg):
    for _ in range(3):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=10,
            )
            d = r.json()
            if d.get("ok"):
                return True
            rt = d.get("parameters", {}).get("retry_after", 0)
            if rt: time.sleep(rt + 1)
        except Exception as e:
            print(f"[TG] {e}")
            time.sleep(2)
    return False


# ═══════════════════════════════════════════
#  HKO — Hong Kong Observatory
# ═══════════════════════════════════════════

def buscar_hko(data_alvo):
    """API oficial do HKO — mesma fonte que o Polymarket usa."""
    ck = f"hko|{data_alvo}"
    if ck in _cache_hko:
        return _cache_hko[ck]
    try:
        # API de dados climáticos diários
        r = requests.get(
            "https://data.weather.gov.hk/weatherAPI/opendata/climate.php",
            params={"dataType": "CLMTEMP", "lang": "en",
                    "rformat": "json", "station": "HKO",
                    "year": data_alvo.year, "month": f"{data_alvo.month:02d}"},
            headers=HEADERS_API, timeout=10,
        )
        if r.status_code == 200:
            d = r.json().get("data", {})
            maxima = d.get("dailyMax", [])
            idx = data_alvo.day - 1
            if maxima and idx < len(maxima) and maxima[idx] not in (None, "***", ""):
                temp = round(float(maxima[idx]), 1)
                _cache_hko[ck] = temp
                return temp
    except Exception as e:
        print(f"  [HKO] {e}")

    # Fallback: API de previsão atual do HKO
    try:
        r2 = requests.get(
            "https://data.weather.gov.hk/weatherAPI/opendata/weather.php",
            params={"dataType": "flw", "lang": "en"},
            headers=HEADERS_API, timeout=8,
        )
        if r2.status_code == 200:
            d2 = r2.json()
            # Extrai temperatura máxima da previsão
            temp_str = str(d2.get("forecastDesc", ""))
            m = re.search(r'maximum.*?(\d+)\s*degrees', temp_str, re.I)
            if m:
                temp = float(m.group(1))
                _cache_hko[ck] = temp
                return temp
    except Exception:
        pass

    return None


# ═══════════════════════════════════════════
#  WUNDERGROUND — estação exata
# ═══════════════════════════════════════════

def buscar_wunderground(station, wu_url, data_alvo, unidade="C"):
    """
    Busca temperatura máxima no Wunderground.
    Esta é a fonte exata que o Polymarket usa para resolver o mercado.
    Usa a API JSON embutida do WU.
    """
    ck = f"wu|{station}|{data_alvo}"
    if ck in _cache_wu:
        return _cache_wu[ck]

    data_str = data_alvo.strftime("%Y%m%d")

    # Método 1: API pública do Weather Company (base do WU)
    try:
        api_url = (
            f"https://api.weather.com/v1/location/{station}:9:US/"
            f"observations/historical.json"
        )
        r = requests.get(
            api_url,
            params={"apiKey": "6532d6454b8aa370768e63d6ba5a832e",
                    "units": "m", "startDate": data_str},
            headers=HEADERS_API, timeout=10,
        )
        if r.status_code == 200:
            obs = r.json().get("observations", [])
            if obs:
                temps = [o.get("metric", {}).get("tempHigh") for o in obs]
                temps = [t for t in temps if t is not None]
                if temps:
                    temp = round(float(max(temps)), 1)
                    if unidade == "F":
                        temp = round((temp - 32) * 5 / 9, 1)
                    _cache_wu[ck] = temp
                    return temp
    except Exception:
        pass

    # Método 2: scraping da página do WU (fallback)
    try:
        url = f"{wu_url}/date/{data_alvo.strftime('%Y-%m-%d')}"
        r = requests.get(url, headers=HEADERS_WEB, timeout=15)
        if r.status_code == 200:
            # Procura padrão JSON no script
            patterns = [
                r'"highTemp"\s*:\s*([\d.]+)',
                r'"temperatureMax"[^}]*"value"\s*:\s*([\d.]+)',
                r'"maxTemp"\s*:\s*([\d.]+)',
                r'High\s*\n\s*(\d+)',
            ]
            for p in patterns:
                m = re.search(p, r.text)
                if m:
                    val = float(m.group(1))
                    # Detecta se é Fahrenheit pelo valor (> 50 em F para temp normal)
                    if unidade == "F" and val > 40:
                        temp = round((val - 32) * 5 / 9, 1)
                    elif unidade == "C" or val < 60:
                        temp = round(val, 1)
                    else:
                        temp = round((val - 32) * 5 / 9, 1)
                    _cache_wu[ck] = temp
                    return temp
    except Exception as e:
        print(f"  [WU scrape] {station}: {e}")

    return None


# ═══════════════════════════════════════════
#  OPEN-METEO — previsão (fallback/futuro)
# ═══════════════════════════════════════════

def buscar_open_meteo(lat, lon, data_alvo):
    """Open-Meteo: gratuito, sem key, usado como fallback e para previsões futuras."""
    ck = f"om|{lat:.2f}|{lon:.2f}|{data_alvo}"
    if ck in _cache_om:
        return _cache_om[ck]
    try:
        hoje = date.today()
        diff = (data_alvo - hoje).days
        if diff < 0 or diff > 15:
            return None
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max", "timezone": "auto",
                    "forecast_days": min(diff + 2, 16)},
            timeout=10,
        )
        d = r.json()
        datas = d.get("daily", {}).get("time", [])
        temps = d.get("daily", {}).get("temperature_2m_max", [])
        ds = data_alvo.strftime("%Y-%m-%d")
        if ds in datas:
            t = temps[datas.index(ds)]
            if t is not None:
                _cache_om[ck] = round(float(t), 1)
                return _cache_om[ck]
    except Exception as e:
        print(f"  [OM] {e}")
    return None


# ═══════════════════════════════════════════
#  ECMWF — via Open-Meteo (modelo europeu)
# ═══════════════════════════════════════════

_cache_ecmwf = {}

def buscar_ecmwf(lat, lon, data_alvo):
    """
    ECMWF (European Centre for Medium-Range Weather Forecasts)
    Modelo mais preciso do mundo para previsão meteorológica.
    Acessado gratuitamente via Open-Meteo.
    """
    ck = f"ecmwf|{lat:.2f}|{lon:.2f}|{data_alvo}"
    if ck in _cache_ecmwf:
        return _cache_ecmwf[ck]
    try:
        hoje = date.today()
        diff = (data_alvo - hoje).days
        if diff < 0 or diff > 10:
            return None
        r = requests.get(
            "https://api.open-meteo.com/v1/ecmwf",
            params={"latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max",
                    "timezone": "auto",
                    "forecast_days": min(diff + 2, 10)},
            timeout=10,
        )
        if r.status_code != 200:
            return None
        d = r.json()
        datas = d.get("daily", {}).get("time", [])
        temps = d.get("daily", {}).get("temperature_2m_max", [])
        ds = data_alvo.strftime("%Y-%m-%d")
        if ds in datas:
            t = temps[datas.index(ds)]
            if t is not None:
                _cache_ecmwf[ck] = round(float(t), 1)
                return _cache_ecmwf[ck]
    except Exception as e:
        print(f"  [ECMWF] {e}")
    return None


# ═══════════════════════════════════════════
#  VALIDAÇÃO WUNDERGROUND
# ═══════════════════════════════════════════

def validar_wunderground(t_wu, t_om, t_ecmwf, cidade):
    """
    Valida se o dado do Wunderground é confiável cruzando com outras fontes.
    Retorna (valido: bool, motivo: str)
    """
    if t_wu is None:
        return False, "WU sem dados"

    fontes_check = []
    if t_om is not None:
        fontes_check.append(("Open-Meteo", t_om))
    if t_ecmwf is not None:
        fontes_check.append(("ECMWF", t_ecmwf))

    if not fontes_check:
        return True, "sem fontes para cruzar (confiando no WU)"

    for nome, t_ref in fontes_check:
        diff = abs(t_wu - t_ref)
        if diff > 8:
            return False, f"WU={t_wu}°C vs {nome}={t_ref}°C (diff {diff:.1f}°C — SUSPEITO)"

    return True, "OK — fontes concordam"


# ═══════════════════════════════════════════
#  OBTER TEMPERATURA — lógica principal
# ═══════════════════════════════════════════

def obter_temperatura(cidade_key, data_alvo):
    """
    Obtém temperatura cruzando 3 fontes:
      1. Wunderground/HKO (fonte oficial do Polymarket)
      2. Open-Meteo (modelo GFS)
      3. ECMWF (modelo europeu — mais preciso do mundo)
    Valida o Wunderground contra as outras fontes.
    """
    cfg = CIDADES.get(cidade_key)
    if not cfg:
        return None

    hoje   = date.today()
    futuro = (data_alvo > hoje)
    lat, lon = cfg["lat"], cfg["lon"]

    t_oficial = None
    fonte_nome = "?"

    if not futuro:
        if cfg["source"] == "hko":
            t_oficial = buscar_hko(data_alvo)
            fonte_nome = "HKO (Hong Kong Observatory)"
        elif cfg["source"] == "wunderground":
            t_oficial = buscar_wunderground(
                cfg["station"], cfg["wu_url"], data_alvo, cfg.get("unidade", "C")
            )
            fonte_nome = f"Wunderground {cfg['station']}"

    # Open-Meteo (modelo GFS)
    t_om = buscar_open_meteo(lat, lon, data_alvo)

    # ECMWF (modelo europeu — mais preciso)
    t_ecmwf = buscar_ecmwf(lat, lon, data_alvo)

    # Validação do Wunderground
    wu_valido = True
    wu_motivo = ""
    if t_oficial is not None and cfg["source"] == "wunderground":
        wu_valido, wu_motivo = validar_wunderground(t_oficial, t_om, t_ecmwf, cidade_key)
        if not wu_valido:
            print(f"  ⚠️ WU INVÁLIDO: {wu_motivo}")
            t_oficial = None  # descarta dado suspeito

    # Calcula mediana e incerteza com todas as fontes disponíveis
    fontes = []
    if t_oficial is not None: fontes.append(t_oficial)
    if t_om is not None:      fontes.append(t_om)
    if t_ecmwf is not None:   fontes.append(t_ecmwf)

    if not fontes:
        return None

    mediana = round(median(fontes), 1)

    if len(fontes) >= 3:
        spread = max(fontes) - min(fontes)
        incerteza = max(spread / 2, 0.5)
    elif len(fontes) == 2:
        incerteza = max(abs(fontes[0] - fontes[1]) / 2, 0.8)
    else:
        incerteza = 2.5 if futuro else 1.5

    # Se fonte oficial existe e é válida, ela tem prioridade
    if t_oficial is not None and wu_valido:
        mediana = t_oficial
        incerteza = min(incerteza, 1.5)

    # Monta nome das fontes usadas
    nomes = []
    if t_oficial is not None: nomes.append(fonte_nome)
    if t_ecmwf is not None:   nomes.append("ECMWF")
    if t_om is not None:      nomes.append("Open-Meteo")
    fonte_str = " + ".join(nomes) if nomes else "?"

    return {
        "mediana":    round(mediana, 1),
        "incerteza":  round(incerteza, 1),
        "t_oficial":  t_oficial,
        "t_om":       t_om,
        "t_ecmwf":    t_ecmwf,
        "fonte":      fonte_str,
        "futuro":     futuro,
        "wu_valido":  wu_valido,
        "wu_motivo":  wu_motivo,
    }


# ═══════════════════════════════════════════
#  POLYMARKET — buscar mercados
# ═══════════════════════════════════════════

def buscar_mercados():
    mercados = []
    for tag in ["temperature", "weather", "daily-temperature"]:
        try:
            r = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={"tag": tag, "active": "true", "closed": "false", "limit": 300},
                headers=HEADERS_API, timeout=15,
            )
            if r.status_code == 200:
                d = r.json()
                mercados.extend(d if isinstance(d, list) else d.get("events", []))
        except Exception as e:
            print(f"  [POLY] {e}")
        time.sleep(0.2)

    vistos, res = set(), []
    for m in mercados:
        cid = m.get("conditionId") or m.get("id") or m.get("slug", "")
        if cid and cid not in vistos:
            vistos.add(cid)
            res.append(m)
    print(f"[POLY] {len(res)} mercados")
    return res


def extrair_info(raw):
    titulo = (raw.get("title") or raw.get("name") or raw.get("question") or "").strip()
    if not titulo or "temperature" not in titulo.lower():
        return None

    cidade = extrair_cidade(titulo.lower())
    if not cidade:
        return None

    data_m = extrair_data(titulo)
    outcomes = []
    slug = raw.get("slug", "")
    cid  = raw.get("conditionId", "")

    # Extrai outcomes de markets[] ou tokens[]
    if "markets" in raw:
        for m in raw["markets"]:
            cid = cid or m.get("conditionId", "")
            for tok in m.get("tokens", []):
                outcomes.append({
                    "outcome": tok.get("outcome", ""),
                    "price":   float(tok.get("price", 0)),
                    "asset_id": tok.get("token_id", ""),
                })
    for tok in raw.get("tokens", []):
        outcomes.append({
            "outcome": tok.get("outcome", ""),
            "price":   float(tok.get("price", 0)),
            "asset_id": tok.get("token_id", ""),
        })

    outcomes = [o for o in outcomes if o["price"] > 0.005]
    if not outcomes:
        return None

    return {"titulo": titulo, "cidade": cidade, "data": data_m,
            "outcomes": outcomes, "slug": slug, "conditionId": cid}


def extrair_cidade(titulo_lower):
    m = re.search(r"temperature\s+in\s+(.+?)\s+on\s", titulo_lower)
    cidade_raw = m.group(1).strip() if m else ""
    if not cidade_raw:
        return None
    if cidade_raw in CIDADES:
        return cidade_raw
    for k in CIDADES:
        if k in cidade_raw or cidade_raw in k:
            return k
    return None


def extrair_data(titulo):
    meses = {"january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
             "july":7,"august":8,"september":9,"october":10,"november":11,"december":12,
             "jan":1,"feb":2,"mar":3,"apr":4,"jun":6,"jul":7,"aug":8,
             "sep":9,"oct":10,"nov":11,"dec":12}
    m = re.search(r'\b(january|february|march|april|may|june|july|august|'
                  r'september|october|november|december|jan|feb|mar|apr|'
                  r'jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})\b', titulo.lower())
    if m and m.group(1) in meses:
        try: return date(date.today().year, meses[m.group(1)], int(m.group(2)))
        except ValueError: pass
    return date.today()


# ═══════════════════════════════════════════
#  EDGE CALCULATION
# ═══════════════════════════════════════════

def parsear_outcome(s):
    s = s.strip()
    f2c = lambda f: round((float(f) - 32) * 5 / 9, 1)

    m = re.match(r'([\d.]+)\s*°?[Cc]?\s*or\s*below', s, re.I)
    if m: return (-99, float(m.group(1)))

    m = re.match(r'([\d.]+)\s*°?[Cc]?\s*or\s*(higher|above|more)', s, re.I)
    if m: return (float(m.group(1)), 99)

    m = re.match(r'([\d.]+)\s*-\s*([\d.]+)\s*°?[Ff]', s)
    if m: return (f2c(m.group(1)), f2c(m.group(2)))

    m = re.match(r'([\d.]+)\s*°?[Ff]$', s)
    if m: v = f2c(m.group(1)); return (v, v)

    m = re.match(r'([\d.]+)\s*-\s*([\d.]+)\s*°?[Cc]?', s)
    if m: return (float(m.group(1)), float(m.group(2)))

    m = re.match(r'([\d.]+)\s*°?[Cc]?$', s)
    if m: return (float(m.group(1)), float(m.group(1)))

    return None


def prob_normal(mu, sigma, fmin, fmax):
    sigma = max(sigma, 0.8)
    def cdf(x): return 0.5 * (1 + math.erf((x - mu) / (sigma * 1.4142)))
    return max(0.0, min(1.0, cdf(fmax + 0.5) - cdf(fmin - 0.5)))


def calcular_edges(outcomes, temp_info):
    mu, sigma = temp_info["mediana"], temp_info["incerteza"]
    res = []
    for o in outcomes:
        faixa = parsear_outcome(o["outcome"])
        if not faixa: continue
        pr = prob_normal(mu, sigma, faixa[0], faixa[1])
        pm = o["price"]
        res.append({
            "outcome":   o["outcome"],
            "prob_real": round(pr * 100, 1),
            "prob_mkt":  round(pm * 100, 1),
            "edge":      round((pr - pm) * 100, 1),
            "price":     pm,
        })
    res.sort(key=lambda x: x["edge"], reverse=True)
    return res


# ═══════════════════════════════════════════
#  TEMPERATURA ATUAL EM TEMPO REAL
# ═══════════════════════════════════════════

def buscar_temp_atual(lat, lon):
    """Busca temperatura ATUAL via Open-Meteo (atualiza a cada 15min)."""
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
                "current": "temperature_2m,apparent_temperature",
                "timezone": "auto",
            },
            timeout=8,
        )
        if r.status_code == 200:
            d = r.json().get("current", {})
            return {
                "temp": round(float(d.get("temperature_2m", 0)), 1),
                "sensacao": round(float(d.get("apparent_temperature", 0)), 1),
                "hora_local": d.get("time", ""),
            }
    except Exception as e:
        print(f"  [TEMP_ATUAL] {e}")
    return None


def analisar_horario(hora_local_str, temp_atual, temp_mediana, cidade_key):
    """
    Analisa se a temperatura ainda pode subir baseado no horário local.
    Retorna (analise_texto, recomendacao)
    """
    try:
        # hora_local_str = "2026-04-16T15:30"
        hora = int(hora_local_str.split("T")[1].split(":")[0])
    except Exception:
        return "", ""

    diff = temp_mediana - temp_atual

    if hora < 11:
        fase = "manhã"
        pode_subir = True
        confianca = "baixa (ainda cedo)"
    elif hora < 14:
        fase = "meio-dia"
        pode_subir = True
        confianca = "média (pico se aproximando)"
    elif hora < 16:
        fase = "tarde (pico de calor)"
        pode_subir = diff > 0
        confianca = "alta (horário de pico)"
    else:
        fase = "fim de tarde"
        pode_subir = False
        confianca = "muito alta (já esfriando)"

    analise = f"⏰ Horário local: <b>{hora}h</b> ({fase})\n"

    if pode_subir and diff > 0.5:
        analise += f"☀️ Pode subir mais <b>+{diff:.1f}°C</b>\n"
    elif not pode_subir:
        analise += f"🌙 Provavelmente <b>não sobe mais</b> — dia esfriando\n"
    else:
        analise += f"📊 Temperatura já próxima do pico\n"

    # Recomendação
    if hora >= 16:
        # Fim do dia — temperatura atual É a máxima
        temp_final = temp_atual
        reco = f"💡 <b>RECO:</b> Apostar na faixa de <b>{int(round(temp_final))}°C</b> (dia acabando)"
    elif hora >= 14:
        # Pico — pode subir 0-1°C
        temp_final = temp_atual + 0.5
        reco = f"💡 <b>RECO:</b> Faixa <b>{int(round(temp_atual))}-{int(round(temp_atual+1))}°C</b> (pico agora)"
    elif hora >= 11:
        # Meio-dia — pode subir 1-3°C
        reco = f"💡 <b>RECO:</b> Faixa <b>{int(round(temp_atual+1))}-{int(round(temp_atual+3))}°C</b> (ainda subindo)"
    else:
        reco = f"💡 <b>RECO:</b> Aguardar — muito cedo pra decidir"

    return analise, reco


# ═══════════════════════════════════════════
#  FORMATAÇÃO
# ═══════════════════════════════════════════

def formatar_alerta(info, temp_info, edges):
    melhores = [e for e in edges if e["edge"] >= MIN_EDGE]
    if not melhores: return None

    cidade   = info["cidade"].title()
    cidade_key = info["cidade"]
    data_str = info["data"].strftime("%d/%m/%Y") if info["data"] else "?"
    slug     = info.get("slug", "")
    link     = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/weather"
    top      = melhores[0]["edge"]

    if top >= 25:   cab = "🔥🔥🔥 EDGE MUITO ALTO"
    elif top >= 15: cab = "🔥🔥 EDGE ALTO"
    elif top >= 10: cab = "🔥 EDGE BOM"
    else:           cab = "✅ EDGE DETECTADO"

    msg  = f"{cab} — <b>{cidade}</b>\n"
    msg += f"📅 {data_str}"
    msg += " ⏰ (amanhã)" if temp_info.get("futuro") else ""
    msg += f"\n━━━━━━━━━━━━━━━━━━━━\n\n"

    # ── TEMPERATURA ATUAL EM TEMPO REAL ──
    cfg = CIDADES.get(cidade_key)
    if cfg and not temp_info.get("futuro"):
        atual = buscar_temp_atual(cfg["lat"], cfg["lon"])
        if atual:
            t_c = atual["temp"]
            t_f = round(t_c * 9/5 + 32)
            station = cfg.get("station", "")
            msg += f"🌡️ <b>Agora em {cidade}:</b>\n"
            msg += f"  {t_f}°F = <b>{t_c}°C</b>"
            if station:
                msg += f" (estação {station})"
            msg += "\n"

            # Análise de horário
            analise, reco = analisar_horario(
                atual.get("hora_local", ""), t_c, temp_info["mediana"], cidade_key
            )
            if analise:
                msg += analise
            if reco:
                msg += reco + "\n"
            msg += "\n"

    # ── FONTES DE PREVISÃO ──
    msg += f"📡 <b>Fontes ({temp_info['fonte']}):</b>\n"
    if temp_info.get("t_oficial"): msg += f"  🎯 Oficial: <b>{temp_info['t_oficial']}°C</b>\n"
    if temp_info.get("t_ecmwf"):   msg += f"  🇪🇺 ECMWF: <b>{temp_info['t_ecmwf']}°C</b>\n"
    if temp_info.get("t_om"):      msg += f"  🌐 Open-Meteo: <b>{temp_info['t_om']}°C</b>\n"
    msg += f"  📊 Central: <b>{temp_info['mediana']}°C ±{temp_info['incerteza']}°C</b>\n"
    if not temp_info.get("wu_valido", True):
        msg += f"  ⚠️ <i>WU descartado: {temp_info.get('wu_motivo','')}</i>\n"
    msg += "\n"

    # ── TABELA DE OPÇÕES DO MERCADO ──
    msg += f"📊 <b>Mercado vs Real:</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━\n"
    for e in edges[:6]:
        if e["edge"] >= MIN_EDGE:
            seta = "🔥"
        elif e["edge"] > 0:
            seta = "⬆️"
        elif e["edge"] > -5:
            seta = "➡️"
        else:
            seta = "⬇️"
        msg += f"{seta} {e['outcome']}: Mkt {e['prob_mkt']}% → Real {e['prob_real']}% (edge {e['edge']:+.0f}%)\n"

    msg += f"\n⚡ <b>MELHORES ENTRADAS:</b>\n"
    for e in melhores[:3]:
        em = "🔥" if e["edge"] >= 15 else "✅"
        msg += f"{em} <b>{e['outcome']}</b> — edge <b>+{e['edge']}%</b> @ {e['price']:.2f}¢\n"

    msg += f"\n🔗 <a href=\"{link}\">Abrir no Polymarket</a>"
    if temp_info["incerteza"] > 2.5:
        msg += f"\n⚠️ <i>Incerteza ±{temp_info['incerteza']}°C — cuidado</i>"
    return msg


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════

def executar_varredura():
    inicio = time.time()
    print(f"\n{'='*55}")
    print(f"  VARREDURA {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*55}")

    raws = buscar_mercados()
    if not raws:
        enviar_telegram("⚠️ Nenhum mercado de temperatura encontrado.")
        return

    total = com_edge = sem_dados = 0
    todas_entradas = []  # coleta TODAS as entradas com edge pra ranking

    for raw in raws:
        try:
            info = extrair_info(raw)
            if not info: continue

            cidade, data_m = info["cidade"], info["data"] or date.today()
            total += 1
            print(f"  → {cidade.title():<15} {data_m.strftime('%d/%m')}", end=" | ")

            temp_info = obter_temperatura(cidade, data_m)
            if not temp_info:
                sem_dados += 1
                print("❌ sem dados")
                continue

            print(f"{temp_info['mediana']}°C ({temp_info['fonte'][:20]})", end=" | ")
            edges   = calcular_edges(info["outcomes"], temp_info)
            melhores = [e for e in edges if e["edge"] >= MIN_EDGE]

            if not melhores:
                best = edges[0]["edge"] if edges else "?"
                print(f"sem edge (melhor: {best}%)")
                continue

            print(f"🔥 edge +{melhores[0]['edge']}%")
            cid = info.get("conditionId") or info["slug"]
            slug = info.get("slug", "")

            for e in melhores:
                # Guarda pra ranking
                todas_entradas.append({
                    "cidade": cidade.title(),
                    "data": data_m.strftime("%d/%m"),
                    "outcome": e["outcome"],
                    "temp_real": temp_info["mediana"],
                    "prob_real": e["prob_real"],
                    "prob_mkt": e["prob_mkt"],
                    "edge": e["edge"],
                    "price": e["price"],
                    "slug": slug,
                    "fonte": temp_info["fonte"],
                    "t_ecmwf": temp_info.get("t_ecmwf"),
                    "t_om": temp_info.get("t_om"),
                    "t_oficial": temp_info.get("t_oficial"),
                    "incerteza": temp_info["incerteza"],
                })

                chave = f"{cid}|{e['outcome']}|{data_m}"
                if chave in alertas_env: continue
                alertas_env.add(chave)

                # Registra entrada no JSON
                registrar_entrada(
                    cidade.title(), data_m.strftime("%d/%m"),
                    e["outcome"], e["edge"], e["prob_real"],
                    e["prob_mkt"], e["price"], slug
                )
                msg = formatar_alerta(info, temp_info, edges)
                if msg:
                    enviar_telegram(msg)
                    com_edge += 1
                    time.sleep(1.5)

        except Exception as ex:
            print(f"\n  [ERRO] {ex}")
        time.sleep(0.1)

    dur = round(time.time() - inicio, 1)

    # ── RANKING: TOP ENTRADAS DO MOMENTO ──
    if todas_entradas:
        todas_entradas.sort(key=lambda x: x["edge"], reverse=True)
        top = todas_entradas[:8]

        rank_msg = (
            f"🏆 <b>TOP ENTRADAS AGORA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
        )
        for i, e in enumerate(top, 1):
            # Mostra temperatura em °C
            temps = []
            if e["t_oficial"] is not None: temps.append(f"WU:{e['t_oficial']}°C")
            if e["t_ecmwf"] is not None:   temps.append(f"ECMWF:{e['t_ecmwf']}°C")
            if e["t_om"] is not None:      temps.append(f"OM:{e['t_om']}°C")
            temp_str = " | ".join(temps) if temps else f"{e['temp_real']}°C"

            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            link = f"https://polymarket.com/event/{e['slug']}" if e["slug"] else ""

            rank_msg += (
                f"\n{medal} <b>{e['cidade']}</b> ({e['data']})\n"
                f"   🌡 {temp_str}\n"
                f"   🎯 {e['outcome']} → Mkt: {e['prob_mkt']}% | Real: {e['prob_real']}%\n"
                f"   ⚡ Edge: <b>+{e['edge']}%</b> | Preço: {e['price']:.2f}¢\n"
            )
            if link:
                rank_msg += f"   🔗 <a href=\"{link}\">Entrar</a>\n"

        rank_msg += f"\n━━━━━━━━━━━━━━━━━━━━\n"
        rank_msg += f"📊 {total} mercados | {len(todas_entradas)} com edge | ±{dur}s"

        enviar_telegram(rank_msg)
        print(f"\n[RANKING] Top {len(top)} entradas enviadas")
    else:
        resumo = (f"📊 <b>VARREDURA</b> — {datetime.now().strftime('%H:%M:%S')}\n"
                  f"━━━━━━━━━━━━━━━━━━━━\n"
                  f"🔍 Analisados: <b>{total}</b>\n"
                  f"❌ Sem edge ≥{MIN_EDGE}%\n"
                  f"❌ Sem dados: <b>{sem_dados}</b>\n"
                  f"⏱️ {dur}s | Próxima: {INTERVALO//60} min")
        enviar_telegram(resumo)

    print(f"\n[RESUMO] {total} analisados | {com_edge} com edge | {sem_dados} sem dados")


def main():
    print("╔══════════════════════════════════════════════════════╗")
    print("║   POLYMARKET WEATHER EDGE BOT v2.0                  ║")
    print("║   Fontes EXATAS do Polymarket por cidade            ║")
    print(f"║   Edge mín: {MIN_EDGE}% | Intervalo: {INTERVALO}s                   ║")
    print("╚══════════════════════════════════════════════════════╝")

    # Mostra mapeamento
    print("\n📡 FONTES CONFIGURADAS:")
    exemplos = ["hong kong","seoul","sao paulo","tel aviv","taipei",
                "karachi","lucknow","new york","london","shanghai"]
    for c in exemplos:
        cfg = CIDADES[c]
        st = cfg.get("station", "HKO")
        print(f"  {c.title():<18} → {cfg['source'].upper()} {st}")
    print(f"  + {len(CIDADES)-len(exemplos)} outras cidades\n")

    enviar_telegram(
        "🤖 <b>Weather Edge Bot v2.0 Ativo!</b>\n\n"
        "📡 <b>Fontes EXATAS do Polymarket:</b>\n"
        "  🇭🇰 Hong Kong → HKO Official\n"
        "  🇰🇷 Seoul → Wunderground RKSI\n"
        "  🇧🇷 São Paulo → Wunderground SBGR\n"
        "  🇮🇱 Tel Aviv → Wunderground LLBG\n"
        "  🇹🇼 Taipei → Wunderground RCSS\n"
        "  🇵🇰 Karachi → Wunderground OPKC\n"
        "  🇮🇳 Lucknow → Wunderground VILK\n"
        "  🇺🇸 NYC → Wunderground KLGA\n"
        "  🇬🇧 London → Wunderground EGLC\n"
        "  🇨🇳 Shanghai → Wunderground ZSPD\n"
        "  + Open-Meteo como complemento\n\n"
        f"⚡ Edge mínimo: <b>{MIN_EDGE}%</b>\n"
        f"⏱️ Varredura a cada <b>{INTERVALO//60} min</b>"
    )

    ciclo = 0
    while True:
        try:
            ciclo += 1
            executar_varredura()

            # A cada 3 ciclos (15min), verifica resultados WIN/LOSS
            if ciclo % 3 == 0:
                print("\n[CHECK] Verificando resultados pendentes...")
                verificar_resultados()

            if ciclo % (6 * 3600 // INTERVALO) == 0:
                alertas_env.clear()
                _cache_wu.clear()
                _cache_hko.clear()
                _cache_om.clear()
                _cache_ecmwf.clear()
                print("[INFO] Cache limpo")
        except KeyboardInterrupt:
            print("\n[INFO] Encerrado.")
            enviar_telegram("🛑 Weather Edge Bot encerrado.")
            break
        except Exception as e:
            import traceback
            traceback.print_exc()
            enviar_telegram(f"⚠️ Erro:\n<code>{str(e)[:200]}</code>\nReiniciando em 60s...")
            time.sleep(60)

        print(f"\n[AGUARDANDO {INTERVALO}s]")
        time.sleep(INTERVALO)


if __name__ == "__main__":
    main()