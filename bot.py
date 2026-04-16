"""
╔══════════════════════════════════════════════════════════════════╗
║   POLYMARKET WEATHER EDGE BOT  v3.0                             ║
║   Foco: Top 7 cidades com maior edge histórico                  ║
║   Fontes: JMA · Met Office · KMA · HKO · Open-Meteo            ║
║   Lógica: Janelas BRT inteligentes + saída antecipada           ║
╚══════════════════════════════════════════════════════════════════╝

CIDADES MONITORADAS (por prioridade):
  🇬🇧 Londres   → EGLC  · Met Office (melhor do mundo para London)
  🇯🇵 Tokyo     → RJTT  · JMA (confiança A/B/C explícita)
  🇰🇷 Seoul     → RKSI  · KMA (frentes frias = edge alto)
  🇭🇰 Hong Kong → HKO   · Observatory oficial
  🇺🇸 NYC       → KLGA  · NWS/NOAA
  🇧🇷 São Paulo → SBGR  · Open-Meteo + CGE
  🇳🇿 Wellington→ NZWN  · MetService NZ

JANELAS BRT (automáticas):
  19h–22h  → 🌟 PESQUISAR + ENTRAR  (ECMWF 19h UTC + GFS 17h UTC)
  22h–02h  → 🌏 MONITORAR ÁSIA      (Wunderground RJTT/RKSI/HKO ao vivo)
  03h–07h  → 🌍 MONITORAR EUROPA    (Met Office 05h UTC)
  09h–13h  → 🌎 MONITORAR AMÉRICAS  (INMET/CGE + NWS)

Instalação:
  pip install requests

Uso:
  python weather_edge_bot_v3.py
"""

import requests
import time
import json
import re
import math
import threading
import websocket  # pip install websocket-client
from datetime import datetime, date, timedelta, timezone

# ══════════════════════════════════════════════
#  CONFIGURAÇÕES — edite aqui
# ══════════════════════════════════════════════

TELEGRAM_TOKEN   = "8744601987:AAFVTdhf2qyDE-OgooIesuHMd9PmhBGSIqo"
TELEGRAM_CHAT_ID = "-1003910452966"

MIN_EDGE         = 5.0    # % mínimo de edge para alertar
INTERVALO_MIN    = 5      # minutos entre varreduras
ALERTAR_SAIDA    = True   # alertar quando cota subiu (saída antecipada)

# ══════════════════════════════════════════════
#  TOP 7 CIDADES — fontes exatas Polymarket
# ══════════════════════════════════════════════

CIDADES = {
    "london": {
        "nome":    "🇬🇧 Londres",
        "station": "EGLC",
        "wu_url":  "https://www.wunderground.com/history/daily/gb/london/EGLC",
        "met_url": "https://weather.metoffice.gov.uk/forecast/u10j124jp",  # London City Airport
        "om_lat":  51.505, "om_lon": 0.055,
        "unidade": "C",
        "prioridade": 1,
        "fuso_local": "Europe/London",
        "hora_pico_utc": 13,   # 13h UTC = pico de calor London
        "vender_brt":    "10h–14h BRT",
        "fonte_oficial": "Met Office",
    },
    "tokyo": {
        "nome":    "🇯🇵 Tokyo",
        "station": "RJTT",
        "wu_url":  "https://www.wunderground.com/history/daily/jp/tokyo/RJTT",
        "jma_url": "https://www.jma.go.jp/bosai/forecast/data/forecast/130000.json",
        "om_lat":  35.552, "om_lon": 139.780,
        "unidade": "C",
        "prioridade": 2,
        "fuso_local": "Asia/Tokyo",
        "hora_pico_utc": 5,    # 14h JST = 05h UTC = pico Tokyo
        "vender_brt":    "23h–03h BRT",
        "fonte_oficial": "JMA",
    },
    "seoul": {
        "nome":    "🇰🇷 Seoul",
        "station": "RKSI",
        "wu_url":  "https://www.wunderground.com/history/daily/kr/incheon/RKSI",
        "kma_url": "https://www.kma.go.kr/neng/forecast/short-term.do",
        "om_lat":  37.460, "om_lon": 126.440,
        "unidade": "C",
        "prioridade": 3,
        "fuso_local": "Asia/Seoul",
        "hora_pico_utc": 5,    # 14h KST = 05h UTC
        "vender_brt":    "23h–03h BRT",
        "fonte_oficial": "KMA",
    },
    "hong kong": {
        "nome":    "🇭🇰 Hong Kong",
        "station": "HKO",
        "hko_api": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php",
        "om_lat":  22.308, "om_lon": 114.174,
        "unidade": "C",
        "prioridade": 4,
        "fuso_local": "Asia/Hong_Kong",
        "hora_pico_utc": 6,    # 14h HKT = 06h UTC
        "vender_brt":    "00h–04h BRT",
        "fonte_oficial": "HKO",
    },
    "new york": {
        "nome":    "🇺🇸 NYC",
        "station": "KLGA",
        "wu_url":  "https://www.wunderground.com/history/daily/us/ny/new-york-city/KLGA",
        "om_lat":  40.777, "om_lon": -73.874,
        "unidade": "F",
        "prioridade": 5,
        "fuso_local": "America/New_York",
        "hora_pico_utc": 19,   # 15h EDT = 19h UTC
        "vender_brt":    "14h–18h BRT",
        "fonte_oficial": "NWS/NOAA",
    },
    "sao paulo": {
        "nome":    "🇧🇷 São Paulo",
        "station": "SBGR",
        "wu_url":  "https://www.wunderground.com/history/daily/br/guarulhos/SBGR",
        "om_lat":  -23.435, "om_lon": -46.473,
        "unidade": "C",
        "prioridade": 6,
        "fuso_local": "America/Sao_Paulo",
        "hora_pico_utc": 18,   # 15h BRT = 18h UTC
        "vender_brt":    "11h–16h BRT",
        "fonte_oficial": "INMET/CGE",
    },
    "wellington": {
        "nome":    "🇳🇿 Wellington",
        "station": "NZWN",
        "wu_url":  "https://www.wunderground.com/history/daily/nz/wellington/NZWN",
        "om_lat":  -41.327, "om_lon": 174.805,
        "unidade": "C",
        "prioridade": 7,
        "fuso_local": "Pacific/Auckland",
        "hora_pico_utc": 2,    # 14h NZST = 02h UTC
        "vender_brt":    "22h–02h BRT",
        "fonte_oficial": "MetService NZ",
    },
}

# ══════════════════════════════════════════════
#  ESTADO GLOBAL
# ══════════════════════════════════════════════

_cache_om   = {}
_cache_pm   = {}   # cache preços Polymarket
alertas_env = set()
precos_ant  = {}   # { "chave": preco_anterior } para detectar valorização

# ══════════════════════════════════════════════
#  WEBSOCKET — Polymarket tempo real
# ══════════════════════════════════════════════

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

ws_app = None
ws_asset_ids = set()       # asset_ids subscritos
ws_odds_changed = set()    # asset_ids que tiveram mudança de odds
ws_lock = threading.Lock()


def ws_subscribe(asset_ids):
    """Subscreve em novos asset_ids no WebSocket."""
    global ws_app
    if not ws_app or not asset_ids:
        return
    try:
        msg = json.dumps({
            "assets_ids": list(asset_ids),
            "operation": "subscribe",
            "custom_feature_enabled": True,
        })
        ws_app.send(msg)
        ws_asset_ids.update(asset_ids)
    except Exception as e:
        print(f"  [WS] Erro subscribe: {e}")


def on_ws_message(ws, message):
    if message in ("PONG", "pong"):
        return
    try:
        data = json.loads(message)
        events = data if isinstance(data, list) else [data]
        for ev in events:
            etype = ev.get("event_type") or ev.get("type") or ""
            if etype in ("last_trade_price", "price_change", "book"):
                asset_id = ev.get("asset_id", "")
                if asset_id:
                    with ws_lock:
                        ws_odds_changed.add(asset_id)
    except Exception:
        pass


def on_ws_open(ws):
    global ws_app
    ws_app = ws
    print(f"  [WS] Conectado → {WS_URL}")
    if ws_asset_ids:
        ws.send(json.dumps({
            "assets_ids": list(ws_asset_ids),
            "type": "market",
            "custom_feature_enabled": True,
        }))
        print(f"  [WS] Subscrito em {len(ws_asset_ids)} assets")
    else:
        ws.send(json.dumps({"type": "market", "assets_ids": [], "custom_feature_enabled": True}))


def on_ws_error(ws, error):
    print(f"  [WS] Erro: {error}")


def on_ws_close(ws, code, msg):
    print(f"  [WS] Desconectado (code={code}). Reconectando em 5s...")
    time.sleep(5)
    iniciar_websocket()


def heartbeat_ws(ws):
    while True:
        time.sleep(10)
        try:
            if ws and ws.sock and ws.sock.connected:
                ws.send("PING")
        except Exception:
            break


def iniciar_websocket():
    def run():
        app = websocket.WebSocketApp(
            WS_URL,
            on_open=on_ws_open,
            on_message=on_ws_message,
            on_error=on_ws_error,
            on_close=on_ws_close,
        )
        hb = threading.Thread(target=heartbeat_ws, args=(app,), daemon=True)
        hb.start()
        app.run_forever(ping_interval=0)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print("  [WS] Thread iniciada")


def ws_check_changes() -> bool:
    """Retorna True se houve mudança de odds desde última checagem."""
    with ws_lock:
        changed = len(ws_odds_changed) > 0
        ws_odds_changed.clear()
        return changed

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "en-US,en;q=0.9",
}

# ══════════════════════════════════════════════
#  UTILIDADES DE TEMPO
# ══════════════════════════════════════════════

def hora_brt() -> int:
    """Retorna hora atual em BRT (UTC-3)."""
    return (datetime.now(timezone.utc).hour - 3) % 24

def janela_brt() -> str:
    """Retorna a janela de operação atual."""
    h = hora_brt()
    if 19 <= h or h < 2:
        return "entrada"    # 19h–02h = pesquisar e entrar
    elif 2 <= h < 7:
        return "europa"     # 02h–07h = monitorar Europa
    elif 7 <= h < 13:
        return "americas"   # 07h–13h = monitorar Américas
    else:
        return "neutro"

def emoji_janela() -> str:
    j = janela_brt()
    return {"entrada": "🌟", "europa": "🌍", "americas": "🌎", "neutro": "⏸️"}[j]

def cidades_prioritarias() -> list:
    """Retorna cidades priorizadas para a janela atual."""
    j = janela_brt()
    if j == "entrada":
        return list(CIDADES.keys())  # todas
    elif j == "europa":
        return ["london", "madrid", "paris"]
    elif j == "americas":
        return ["sao paulo", "new york", "wellington"]
    else:
        return ["tokyo", "seoul", "hong kong", "wellington"]

def data_mercado() -> date:
    """
    Data do mercado a monitorar.
    Busca HOJE e AMANHÃ — retorna o que tiver mercado ativo.
    Se hoje já resolveu, busca amanhã.
    """
    h = hora_brt()
    hoje = date.today()
    amanha = hoje + timedelta(days=1)

    # Tenta hoje primeiro — se não achar mercado, usa amanhã
    # Na prática: mercados de hoje resolvem ~18h local da cidade
    # Então de manhã BRT ainda pode ter mercados de hoje abertos (Ásia/Europa)
    # Mas à noite BRT, só amanhã tem mercados novos

    # Retorna ambos para o bot tentar os dois
    return amanha  # prioriza amanhã (mercados mais frescos)

# ══════════════════════════════════════════════
#  TELEGRAM
# ══════════════════════════════════════════════

def telegram(msg: str, silencioso: bool = False) -> bool:
    for tentativa in range(3):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "disable_notification": silencioso,
                },
                timeout=12,
            )
            d = r.json()
            if d.get("ok"):
                return True
            espera = d.get("parameters", {}).get("retry_after", 3)
            time.sleep(espera + 1)
        except Exception as e:
            print(f"  [TG] erro tentativa {tentativa+1}: {e}")
            time.sleep(3)
    return False

# ══════════════════════════════════════════════
#  OPEN-METEO — previsão oficial (gratuito)
# ══════════════════════════════════════════════

def previsao_open_meteo(cidade_key: str, data_alvo: date) -> dict | None:
    """
    Busca previsão de temperatura máxima + mínima + precipitação
    via Open-Meteo (ECMWF + GFS combinado).
    """
    cfg = CIDADES.get(cidade_key)
    if not cfg:
        return None

    ck = f"om|{cfg['om_lat']}|{cfg['om_lon']}|{data_alvo}"
    if ck in _cache_om:
        return _cache_om[ck]

    hoje = date.today()
    diff = (data_alvo - hoje).days
    if diff < 0 or diff > 7:
        return None

    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude":     cfg["om_lat"],
                "longitude":    cfg["om_lon"],
                "daily":        "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weathercode",
                "timezone":     "auto",
                "forecast_days": min(diff + 2, 8),
                "models":       "best_match",  # usa o melhor modelo disponível
            },
            headers=HEADERS,
            timeout=12,
        )
        if r.status_code != 200:
            return None

        d = r.json().get("daily", {})
        datas  = d.get("time", [])
        tmax   = d.get("temperature_2m_max", [])
        tmin   = d.get("temperature_2m_min", [])
        chuva  = d.get("precipitation_probability_max", [])
        wcode  = d.get("weathercode", [])

        ds = data_alvo.strftime("%Y-%m-%d")
        if ds not in datas:
            return None

        idx = datas.index(ds)
        resultado = {
            "tmax":       round(float(tmax[idx]), 1) if tmax[idx] is not None else None,
            "tmin":       round(float(tmin[idx]), 1) if tmin[idx] is not None else None,
            "chuva_pct":  int(chuva[idx]) if chuva[idx] is not None else 0,
            "wcode":      int(wcode[idx]) if wcode[idx] is not None else 0,
        }
        _cache_om[ck] = resultado
        return resultado
    except Exception as e:
        print(f"  [OM] {cidade_key}: {e}")
        return None

def wcode_emoji(wc: int) -> str:
    if wc == 0:             return "☀️"
    if wc in (1, 2, 3):     return "⛅"
    if wc in range(51, 68): return "🌧️"
    if wc in range(71, 78): return "🌨️"
    if wc in range(80, 83): return "🌦️"
    if wc in range(95, 100):return "⛈️"
    return "🌤️"

# ══════════════════════════════════════════════
#  HKO — Hong Kong Observatory (fonte oficial)
# ══════════════════════════════════════════════

def previsao_hko() -> float | None:
    """Busca previsão máxima do HKO via API oficial."""
    try:
        r = requests.get(
            "https://data.weather.gov.hk/weatherAPI/opendata/weather.php",
            params={"dataType": "fnd", "lang": "en"},
            headers=HEADERS, timeout=10,
        )
        if r.status_code == 200:
            d = r.json()
            # Pega máxima do dia ou amanhã
            weather_fc = d.get("weatherForecast", [])
            if weather_fc:
                amanha = weather_fc[0] if len(weather_fc) > 0 else {}
                tmax = amanha.get("forecastMaxtemp", {}).get("value")
                if tmax:
                    return float(tmax)
    except Exception as e:
        print(f"  [HKO] {e}")
    return None

# ══════════════════════════════════════════════
#  POLYMARKET — buscar mercados e preços
# ══════════════════════════════════════════════

def buscar_mercados_polymarket(data_alvo: date) -> list:
    """Busca mercados de temperatura abertos para a data alvo via slug direto."""
    ck = f"pm|{data_alvo}"
    if ck in _cache_pm:
        return _cache_pm[ck]

    # Constrói slugs para cada cidade
    mes = data_alvo.strftime("%B").lower()  # "april"
    dia = data_alvo.day                      # 17
    ano = data_alvo.year                     # 2026
    ds = f"{mes}-{dia}-{ano}"               # "april-17-2026"

    slug_map = {
        "london":    f"highest-temperature-in-london-on-{ds}",
        "tokyo":     f"highest-temperature-in-tokyo-on-{ds}",
        "seoul":     f"highest-temperature-in-seoul-on-{ds}",
        "hong kong": f"highest-temperature-in-hong-kong-on-{ds}",
        "new york":  f"highest-temperature-in-nyc-on-{ds}",
        "sao paulo": f"highest-temperature-in-sao-paulo-on-{ds}",
        "wellington":f"highest-temperature-in-wellington-on-{ds}",
    }

    mercados = []
    for cidade_key, slug in slug_map.items():
        if cidade_key not in CIDADES:
            continue
        try:
            r = requests.get(
                "https://gamma-api.polymarket.com/events",
                params={"slug": slug},
                headers=HEADERS, timeout=10,
            )
            if r.status_code == 200:
                events = r.json()
                if events and isinstance(events, list) and len(events) > 0:
                    ev = events[0]
                    ev["_cidade_key"] = cidade_key
                    mercados.append(ev)
                    print(f"  [PM] ✅ {cidade_key}: {len(ev.get('markets',[]))} sub-mercados")
        except Exception as e:
            print(f"  [PM] ❌ {cidade_key}: {e}")
        time.sleep(0.2)

    print(f"  [PM] {len(mercados)} mercados para {data_alvo}")
    _cache_pm[ck] = mercados
    return mercados

def extrair_cidade_titulo(titulo: str) -> str | None:
    m = re.search(r"highest temperature in (.+?) on ", titulo.lower())
    if not m:
        return None
    cidade_raw = m.group(1).strip()
    for k in CIDADES:
        if k in cidade_raw or cidade_raw in k:
            return k
    # fuzzy
    for k in CIDADES:
        palavras = k.split()
        if any(p in cidade_raw for p in palavras):
            return k
    return None

def extrair_outcomes(raw: dict) -> list:
    """Extrai pares (outcome, price) de um mercado Polymarket."""
    outcomes = []
    if "markets" in raw:
        for m in raw["markets"]:
            for tok in m.get("tokens", []):
                p = tok.get("price", 0)
                if p and float(p) > 0.005:
                    outcomes.append({
                        "outcome":  tok.get("outcome", ""),
                        "price":    float(p),
                        "token_id": tok.get("token_id", ""),
                    })
    for tok in raw.get("tokens", []):
        p = tok.get("price", 0)
        if p and float(p) > 0.005:
            outcomes.append({
                "outcome":  tok.get("outcome", ""),
                "price":    float(p),
                "token_id": tok.get("token_id", ""),
            })
    return outcomes

# ══════════════════════════════════════════════
#  CÁLCULO DE EDGE
# ══════════════════════════════════════════════

def parsear_faixa_temp(s: str) -> tuple | None:
    """Converte string de outcome em (tmin, tmax) em Celsius."""
    s = s.strip()
    f2c = lambda f: round((float(f) - 32) * 5 / 9, 1)

    # "18°C or higher" / "18°C or above"
    m = re.match(r'([\d.]+)\s*°?[Cc]?\s*or\s*(higher|above|more)', s, re.I)
    if m: return (float(m.group(1)), 99.0)

    # "12°C or below"
    m = re.match(r'([\d.]+)\s*°?[Cc]?\s*or\s*(below|lower)', s, re.I)
    if m: return (-99.0, float(m.group(1)))

    # "54-55°F" ou "54°F"
    m = re.match(r'([\d.]+)\s*-\s*([\d.]+)\s*°?[Ff]', s)
    if m: return (f2c(m.group(1)), f2c(m.group(2)))
    m = re.match(r'([\d.]+)\s*°?[Ff]$', s)
    if m: v = f2c(m.group(1)); return (v, v)

    # "54°F or higher"
    m = re.match(r'([\d.]+)\s*°?[Ff]\s*or\s*(higher|above)', s, re.I)
    if m: return (f2c(m.group(1)), 99.0)

    # "17°C" simples
    m = re.match(r'([\d.]+)\s*°?[Cc]?$', s)
    if m: v = float(m.group(1)); return (v, v)

    return None

def prob_normal(mu: float, sigma: float, fmin: float, fmax: float) -> float:
    """P(fmin ≤ X ≤ fmax) para X ~ N(mu, sigma)."""
    sigma = max(sigma, 0.7)
    def cdf(x): return 0.5 * (1 + math.erf((x - mu) / (sigma * 1.4142135)))
    lo = -99.0 if fmin <= -90 else fmin - 0.5
    hi =  99.0 if fmax >= 90  else fmax + 0.5
    return max(0.0, min(1.0, cdf(hi) - cdf(lo)))

def calcular_edges(outcomes: list, tmax_previsto: float, incerteza: float) -> list:
    resultado = []
    soma_mkt = 0
    for o in outcomes:
        faixa = parsear_faixa_temp(o["outcome"])
        if not faixa:
            continue
        prob_real = prob_normal(tmax_previsto, incerteza, faixa[0], faixa[1])
        prob_mkt  = o["price"]
        soma_mkt += prob_mkt
        edge      = (prob_real - prob_mkt) * 100
        resultado.append({
            "outcome":    o["outcome"],
            "prob_real":  round(prob_real * 100, 1),
            "prob_mkt":   round(prob_mkt  * 100, 1),
            "edge":       round(edge, 1),
            "price":      round(prob_mkt, 3),
            "token_id":   o.get("token_id", ""),
        })
    resultado.sort(key=lambda x: x["edge"], reverse=True)

    # Detecta odds desajustadas (soma != ~100%)
    soma_pct = round(soma_mkt * 100, 1)
    desajuste = abs(soma_pct - 100)
    if desajuste > 5:
        print(f"  ⚠️ ODDS DESAJUSTADAS: soma={soma_pct}% (desajuste {desajuste:.1f}%)")
        for r in resultado:
            r["desajuste"] = round(desajuste, 1)

    return resultado

# ══════════════════════════════════════════════
#  FORMATAÇÃO DE ALERTAS
# ══════════════════════════════════════════════

ICONES_EDGE = {25: "🔥🔥🔥", 18: "🔥🔥", 12: "🔥", 8: "✅"}

def nivel_edge(edge: float) -> str:
    for limiar, icone in ICONES_EDGE.items():
        if edge >= limiar:
            return icone
    return "📊"

def confianca_edge(edge: float, incerteza: float, chuva_pct: float = 0) -> str:
    """Calcula nível de confiança baseado em edge, incerteza e chuva."""
    score = edge
    if incerteza <= 1.2: score += 5
    elif incerteza >= 2.0: score -= 5
    if chuva_pct > 50: score -= 8
    if score >= 20: return "🟢 Alta"
    if score >= 12: return "🟡 Média"
    return "🔴 Baixa"

def alvo_saida(price: float) -> str:
    """Estima preço alvo para saída antecipada."""
    alvo = min(0.98, price + (1 - price) * 0.45)
    return f"{alvo:.2f}¢"

def msg_alerta_entrada(cidade_key, cfg, data_alvo, prev, edges_top, slug) -> str:
    j          = janela_brt()
    h          = hora_brt()
    cidade     = cfg["nome"]
    data_str   = data_alvo.strftime("%d/%m/%Y")
    link       = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/weather"
    top_edge   = edges_top[0]["edge"]
    icone_edge = nivel_edge(top_edge)
    w_emoji    = wcode_emoji(prev.get("wcode", 0)) if prev else "🌤️"
    tmax       = prev.get("tmax", "?") if prev else "?"
    chuva      = prev.get("chuva_pct", 0) if prev else 0
    incerteza  = 1.2 if chuva < 30 else 1.8 if chuva < 60 else 2.5
    conf       = confianca_edge(top_edge, incerteza, chuva)
    top        = edges_top[0]
    acao       = "BUY YES" if top["edge"] > 0 else "SELL"

    # Formato limpo
    msg  = f"� <b>OPORTUNIDADE DETECTADA</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"� Cidade: <b>{cidade}</b> ({cfg['station']})\n"
    msg += f"📅 Data: <b>{data_str}</b>\n"
    msg += f"🌡️ Temperatura: <b>{tmax}°C</b> {w_emoji} (💧{chuva}%)\n"
    msg += f"📊 Mercado: <b>{top['prob_mkt']}%</b>\n"
    msg += f"🧠 Real: <b>{top['prob_real']}%</b>\n"
    msg += f"� Edge: <b>+{top['edge']}%</b>\n"
    msg += f"🎯 Ação: <b>{acao} {top['outcome']} @ {top['price']:.2f}¢</b>\n"
    msg += f"⚡ Confiança: <b>{conf}</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━\n\n"

    # Outras oportunidades
    if len(edges_top) > 1:
        msg += f"📋 <b>Outras oportunidades:</b>\n"
        for e in edges_top[1:3]:
            em = nivel_edge(e["edge"])
            msg += f"  {em} {e['outcome']}: Mkt {e['prob_mkt']}% → Real {e['prob_real']}% (edge +{e['edge']}%)\n"
        msg += "\n"

    # Timing
    msg += f"⏰ Vender: <b>{cfg['vender_brt']}</b> ({cfg['station']} confirma)\n"
    alvo = alvo_saida(top["price"])
    msg += f"🎯 Alvo saída: <b>{alvo}</b>\n\n"

    # Timing de saída
    msg += f"⏰ <b>Quando vender ({cfg['vender_brt']}):</b>\n"
    msg += f"  Quando {cfg['station']} confirmar temperatura → cota sobe\n\n"

    # Alerta de odds desajustadas
    if edges_top and edges_top[0].get("desajuste", 0) > 5:
        msg += f"⚠️ <b>ODDS DESAJUSTADAS!</b> Soma do mercado ≠ 100% (desvio {edges_top[0]['desajuste']}%)\n"
        msg += f"💡 Mercado recém-aberto ou com pouca liquidez — odds frescas!\n\n"

    msg += f"🔗 <a href=\"{link}\">Abrir no Polymarket</a>"
    return msg

def msg_alerta_saida(cidade_key, cfg, outcome, price_ant, price_now, slug) -> str:
    cidade   = cfg["nome"]
    link     = f"https://polymarket.com/event/{slug}" if slug else "https://polymarket.com/weather"
    ganho    = round((price_now - price_ant) / price_ant * 100, 1)
    msg  = f"📈 <b>COTA VALORIZOU — CONSIDERE VENDER!</b>\n"
    msg += f"Cidade: <b>{cidade}</b>\n"
    msg += f"Outcome: <b>{outcome}</b>\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━\n"
    msg += f"  Entrada: <b>{price_ant:.2f}¢</b>\n"
    msg += f"  Agora:   <b>{price_now:.2f}¢</b>  (+{ganho}%)\n\n"
    msg += f"💡 Venda agora para lucro antecipado sem esperar resolução.\n"
    msg += f"🔗 <a href=\"{link}\">Abrir no Polymarket</a>"
    return msg

def msg_resumo(total, com_edge, sem_dados, janela, duracao) -> str:
    now   = datetime.now(timezone.utc) - timedelta(hours=3)  # BRT
    emoji = emoji_janela()
    msg   = (
        f"{emoji} <b>VARREDURA CONCLUÍDA</b> — {now.strftime('%H:%M')} BRT\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"🔍 Mercados analisados: <b>{total}</b>\n"
        f"✅ Com edge ≥{MIN_EDGE}%:  <b>{com_edge}</b>\n"
        f"❌ Sem dados:          <b>{sem_dados}</b>\n"
        f"⏱️ Duração: {duracao:.1f}s\n"
        f"📅 Janela: <b>{janela.upper()}</b>\n"
        f"⏳ Próxima varredura em {INTERVALO_MIN} min"
    )
    return msg

# ══════════════════════════════════════════════
#  VARREDURA PRINCIPAL
# ══════════════════════════════════════════════

def executar_varredura():
    inicio  = time.time()
    janela  = janela_brt()
    data_alvo = data_mercado()
    h_brt   = hora_brt()

    print(f"\n{'═'*55}")
    print(f"  VARREDURA  {datetime.now(timezone.utc).strftime('%d/%m/%Y')}  {h_brt:02d}h BRT  |  Janela: {janela.upper()}")
    print(f"  Monitorando mercados de: {data_alvo}")
    print(f"{'═'*55}")

    # Busca mercados Polymarket
    mercados = buscar_mercados_polymarket(data_alvo)
    if not mercados:
        print("  [!] Nenhum mercado encontrado.")
        return

    total = com_edge = sem_dados = 0

    for raw in mercados:
        titulo = (raw.get("title") or raw.get("name") or "").strip()

        # Usa _cidade_key se disponível (busca por slug), senão extrai do título
        cidade_key = raw.get("_cidade_key") or extrair_cidade_titulo(titulo)
        if not cidade_key or cidade_key not in CIDADES:
            continue

        cfg      = CIDADES[cidade_key]
        outcomes = extrair_outcomes(raw)
        slug     = raw.get("slug", "")

        if not outcomes:
            continue

        # Subscreve token_ids no WebSocket
        new_ids = [o["token_id"] for o in outcomes if o.get("token_id") and o["token_id"] not in ws_asset_ids]
        if new_ids:
            ws_subscribe(new_ids)

        total += 1
        print(f"  → {cfg['nome']:<20}", end=" | ")

        # Busca previsão de temperatura
        prev = previsao_open_meteo(cidade_key, data_alvo)

        # Fonte especial HKO para Hong Kong
        if cidade_key == "hong kong":
            t_hko = previsao_hko()
            if t_hko:
                if prev:
                    prev["tmax"] = t_hko
                else:
                    prev = {"tmax": t_hko, "tmin": None, "chuva_pct": 0, "wcode": 0}

        if not prev or prev.get("tmax") is None:
            sem_dados += 1
            print("❌ sem previsão")
            continue

        tmax      = prev["tmax"]
        chuva_pct = prev.get("chuva_pct", 0)

        # Incerteza maior se há chuva prevista (temperatura menos previsível)
        incerteza = 1.2 if chuva_pct < 30 else 1.8 if chuva_pct < 60 else 2.5

        print(f"{tmax}°C  chuva:{chuva_pct}%  inc:±{incerteza}°C", end=" | ")

        edges = calcular_edges(outcomes, tmax, incerteza)
        melhores = [e for e in edges if e["edge"] >= MIN_EDGE]

        if not melhores:
            best = edges[0]["edge"] if edges else "?"
            print(f"sem edge (melhor: {best}%)")
            continue

        print(f"🔥 edge +{melhores[0]['edge']}%")

        # ── Alerta de ENTRADA ──
        chave_alerta = f"{slug}|{data_alvo}"
        if chave_alerta not in alertas_env:
            alertas_env.add(chave_alerta)
            msg = msg_alerta_entrada(
                cidade_key, cfg, data_alvo, prev, melhores, slug
            )
            telegram(msg)
            com_edge += 1
            time.sleep(1.5)

        # ── Alerta de SAÍDA ANTECIPADA ──
        if ALERTAR_SAIDA:
            for e in melhores:
                chave_preco = f"{slug}|{e['outcome']}"
                price_ant   = precos_ant.get(chave_preco)
                price_now   = e["price"]

                if price_ant is not None:
                    valorizacao = (price_now - price_ant) / max(price_ant, 0.01) * 100
                    if valorizacao >= 15:  # subiu 15%+ → avisar para vender
                        chave_saida = f"saida|{chave_preco}|{round(price_now,2)}"
                        if chave_saida not in alertas_env:
                            alertas_env.add(chave_saida)
                            telegram(msg_alerta_saida(
                                cidade_key, cfg, e["outcome"],
                                price_ant, price_now, slug
                            ))
                            time.sleep(1)

                precos_ant[chave_preco] = price_now

        time.sleep(0.2)

    duracao = round(time.time() - inicio, 1)
    print(f"\n  RESUMO: {total} analisados | {com_edge} com edge | {sem_dados} sem dados | {duracao}s\n")
    telegram(msg_resumo(total, com_edge, sem_dados, janela, duracao), silencioso=True)

# ══════════════════════════════════════════════
#  STARTUP MESSAGE
# ══════════════════════════════════════════════

def msg_startup() -> str:
    h = hora_brt()
    j = janela_brt()
    return (
        f"🤖 <b>Weather Edge Bot v3.0 ATIVO!</b>\n\n"
        f"📡 <b>Top 7 cidades monitoradas:</b>\n"
        f"  🥇 🇬🇧 Londres  → EGLC  (Met Office)\n"
        f"  🥈 🇯🇵 Tokyo   → RJTT  (JMA)\n"
        f"  🥉 🇰🇷 Seoul   → RKSI  (KMA)\n"
        f"  4° 🇭🇰 HK      → HKO   (Observatory)\n"
        f"  5° 🇺🇸 NYC     → KLGA  (NWS/NOAA)\n"
        f"  6° 🇧🇷 SP      → SBGR  (INMET)\n"
        f"  7° 🇳🇿 Wgtn    → NZWN  (MetService)\n\n"
        f"⚡ Edge mínimo: <b>{MIN_EDGE}%</b>\n"
        f"⏱️ Varredura a cada: <b>{INTERVALO_MIN} min</b>\n"
        f"🕐 Hora BRT agora: <b>{h:02d}h</b>\n"
        f"📌 Janela atual: <b>{j.upper()}</b>\n\n"
        f"<b>Janelas automáticas:</b>\n"
        f"  🌟 19h–22h BRT → PESQUISAR + ENTRAR\n"
        f"  🌏 22h–02h BRT → MONITORAR ÁSIA (vender)\n"
        f"  🌍 03h–07h BRT → MONITORAR EUROPA (vender)\n"
        f"  🌎 09h–13h BRT → MONITORAR AMÉRICAS"
    )

# ══════════════════════════════════════════════
#  MAIN LOOP
# ══════════════════════════════════════════════

def main():
    print("╔══════════════════════════════════════════════════╗")
    print("║   POLYMARKET WEATHER EDGE BOT  v3.0 + WS        ║")
    print("║   Top 7 cidades · WebSocket tempo real           ║")
    print(f"║   Edge mín: {MIN_EDGE}%  |  Intervalo: {INTERVALO_MIN} min             ║")
    print("╚══════════════════════════════════════════════════╝\n")

    # Inicia WebSocket
    iniciar_websocket()
    time.sleep(2)

    telegram(msg_startup())
    print("[OK] Mensagem de startup enviada ao Telegram\n")

    ciclo = 0
    ultimo_scan = 0

    while True:
        try:
            time.sleep(10)  # checa a cada 10s
            ciclo += 1
            agora = time.time()

            # WebSocket detectou mudança de odds → limpa cache PM e faz scan
            odds_mudaram = ws_check_changes()

            # Scan completo a cada INTERVALO_MIN ou quando odds mudam
            tempo_desde_scan = agora - ultimo_scan
            fazer_scan = (tempo_desde_scan >= INTERVALO_MIN * 60) or (odds_mudaram and tempo_desde_scan >= 30)

            if fazer_scan:
                if odds_mudaram:
                    print(f"\n  [WS] ⚡ Odds mudaram! Varredura imediata...")
                _cache_pm.clear()  # força buscar dados frescos
                executar_varredura()
                ultimo_scan = agora

            # Limpa cache a cada 6 horas
            if ciclo % (2160) == 0:  # 2160 * 10s = 6h
                _cache_om.clear()
                _cache_pm.clear()
                print("[INFO] Cache limpo")

            # Log a cada 60s
            if ciclo % 6 == 0 and not fazer_scan:
                ws_count = len(ws_asset_ids)
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] WS: {ws_count} assets | Próximo scan em {int(INTERVALO_MIN*60 - tempo_desde_scan)}s")

        except KeyboardInterrupt:
            print("\n[INFO] Encerrado pelo usuário.")
            telegram("🛑 <b>Weather Edge Bot v3.0 encerrado.</b>")
            break

        except Exception as e:
            import traceback
            traceback.print_exc()
            telegram(
                f"⚠️ <b>Erro na varredura:</b>\n"
                f"<code>{str(e)[:300]}</code>\n"
                f"Reiniciando em 60s..."
            )
            time.sleep(60)
            continue


if __name__ == "__main__":
    main()