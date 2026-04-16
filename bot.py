"""
Seoul Weather Bot — Wunderground + Polymarket → Telegram
Pega temperatura real via Selenium, % do mercado, previsão 5 dias.
"""

import os, json, re, time, requests
from datetime import date, datetime, timedelta

os.environ["PYTHONUNBUFFERED"] = "1"

# ═══════════════════════════════════════════
#  CONFIGURAÇÕES
# ═══════════════════════════════════════════

TELEGRAM_TOKEN   = "8744601987:AAFVTdhf2qyDE-OgooIesuHMd9PmhBGSIqo"
TELEGRAM_CHAT_ID = "-1003910452966"
INTERVALO        = 300  # 5 minutos

# Wunderground
WU_TODAY = "https://www.wunderground.com/weather/kr/incheon/RKSI"
WU_10DAY = "https://www.wunderground.com/forecast/kr/incheon/RKSI"
WU_HIST  = "https://www.wunderground.com/history/daily/kr/incheon/RKSI"

# Polymarket Seoul
POLY_SLUG_BASE = "highest-temperature-in-seoul-on-"
GAMMA_API = "https://gamma-api.polymarket.com"

H_API = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}


# ═══════════════════════════════════════════
#  TELEGRAM
# ═══════════════════════════════════════════

def enviar(msg):
    for _ in range(3):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg,
                      "parse_mode": "HTML", "disable_web_page_preview": True},
                timeout=10)
            if r.json().get("ok"): return True
            rt = r.json().get("parameters", {}).get("retry_after", 0)
            if rt: time.sleep(rt + 1); continue
            # Fallback sem HTML
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg}, timeout=10)
            return True
        except Exception as e:
            print(f"[TG] {e}"); time.sleep(2)
    return False


# ═══════════════════════════════════════════
#  SELENIUM — Wunderground
# ═══════════════════════════════════════════

_driver = None

def get_driver():
    """Cria driver Chrome headless."""
    global _driver
    if _driver:
        return _driver
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--lang=en-US")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    _driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=opts
    )
    _driver.implicitly_wait(10)
    return _driver


def buscar_temp_wunderground():
    """Pega temperatura atual + máxima de hoje do Wunderground via Selenium."""
    try:
        driver = get_driver()
        driver.get(WU_TODAY)
        time.sleep(5)

        html = driver.page_source

        # Temperatura atual
        temp_atual = None
        m = re.search(r'class="current-temp"[^>]*>.*?(\d+)\s*°', html, re.S)
        if m:
            temp_atual = int(m.group(1))

        # Máxima/Mínima do dia
        temp_max = temp_min = None
        m = re.search(r'HIGH\s*(\d+)\s*°\s*C', html, re.I)
        if m: temp_max = int(m.group(1))
        m = re.search(r'LOW\s*(\d+)\s*°\s*C', html, re.I)
        if m: temp_min = int(m.group(1))

        # Fallback: pega do texto geral
        if not temp_atual:
            m = re.search(r'"temperature"[^}]*"value"\s*:\s*([\d.]+)', html)
            if m: temp_atual = round(float(m.group(1)))

        print(f"[WU] Atual: {temp_atual}°C | Max: {temp_max}°C | Min: {temp_min}°C")
        return {"atual": temp_atual, "max": temp_max, "min": temp_min}

    except Exception as e:
        print(f"[WU] Erro: {e}")
        return {"atual": None, "max": None, "min": None}


def buscar_previsao_5dias():
    """Pega previsão 5 dias do Wunderground via Selenium."""
    try:
        driver = get_driver()
        driver.get(WU_10DAY)
        time.sleep(5)

        html = driver.page_source
        previsao = []

        # Padrão: datas com max/min
        # Busca blocos de previsão diária
        dias = re.findall(
            r'(\d{1,2}/\d{2}).*?(\d+)°\s*\|\s*(\d+)°\s*C',
            html, re.S
        )

        if not dias:
            # Fallback: Open-Meteo
            return buscar_previsao_openmeteo()

        for d, mx, mn in dias[:5]:
            previsao.append({"data": d, "max": int(mx), "min": int(mn)})

        return previsao

    except Exception as e:
        print(f"[WU 10day] Erro: {e}")
        return buscar_previsao_openmeteo()


def buscar_previsao_openmeteo():
    """Fallback: previsão via Open-Meteo GFS (gratuito, sem Selenium)."""
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast",
            params={"latitude": 37.46, "longitude": 126.44,
                    "daily": "temperature_2m_max,temperature_2m_min",
                    "timezone": "Asia/Seoul", "forecast_days": 6},
            timeout=10)
        d = r.json().get("daily", {})
        datas = d.get("time", [])
        maxs = d.get("temperature_2m_max", [])
        mins = d.get("temperature_2m_min", [])
        prev = []
        for i in range(min(5, len(datas))):
            dt = datetime.strptime(datas[i], "%Y-%m-%d")
            prev.append({
                "data": dt.strftime("%d/%m"),
                "max": round(maxs[i], 1),
                "min": round(mins[i], 1),
            })
        return prev
    except Exception as e:
        print(f"[GFS] Erro: {e}")
        return []


def buscar_modelos_amanha():
    """
    Busca previsão de máxima para AMANHÃ em Seoul usando 3 modelos:
      - GFS (Open-Meteo padrão)
      - ECMWF (modelo europeu — mais preciso do mundo)
      - Open-Meteo Best Match (ensemble)
    Retorna dict com cada modelo.
    """
    amanha = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    lat, lon = 37.46, 126.44
    resultado = {"gfs": None, "ecmwf": None, "best": None, "data": amanha}

    # GFS
    try:
        r = requests.get("https://api.open-meteo.com/v1/gfs",
            params={"latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max", "timezone": "Asia/Seoul",
                    "forecast_days": 3}, timeout=10)
        d = r.json().get("daily", {})
        datas = d.get("time", [])
        maxs = d.get("temperature_2m_max", [])
        if amanha in datas:
            resultado["gfs"] = round(maxs[datas.index(amanha)], 1)
            print(f"  [GFS] Amanhã: {resultado['gfs']}°C")
    except Exception as e:
        print(f"  [GFS] Erro: {e}")

    # ECMWF
    try:
        r = requests.get("https://api.open-meteo.com/v1/ecmwf",
            params={"latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max", "timezone": "Asia/Seoul",
                    "forecast_days": 3}, timeout=10)
        d = r.json().get("daily", {})
        datas = d.get("time", [])
        maxs = d.get("temperature_2m_max", [])
        if amanha in datas:
            resultado["ecmwf"] = round(maxs[datas.index(amanha)], 1)
            print(f"  [ECMWF] Amanhã: {resultado['ecmwf']}°C")
    except Exception as e:
        print(f"  [ECMWF] Erro: {e}")

    # Best Match (ensemble de modelos)
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast",
            params={"latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max", "timezone": "Asia/Seoul",
                    "forecast_days": 3}, timeout=10)
        d = r.json().get("daily", {})
        datas = d.get("time", [])
        maxs = d.get("temperature_2m_max", [])
        if amanha in datas:
            resultado["best"] = round(maxs[datas.index(amanha)], 1)
            print(f"  [BEST] Amanhã: {resultado['best']}°C")
    except Exception as e:
        print(f"  [BEST] Erro: {e}")

    # Média dos modelos
    vals = [v for v in [resultado["gfs"], resultado["ecmwf"], resultado["best"]] if v is not None]
    resultado["media"] = round(sum(vals) / len(vals), 1) if vals else None

    return resultado


# ═══════════════════════════════════════════
#  POLYMARKET — % por grau
# ═══════════════════════════════════════════

def buscar_polymarket_seoul(data_alvo):
    """Busca outcomes e % do mercado de Seoul na Polymarket."""
    meses = {1:"january",2:"february",3:"march",4:"april",5:"may",6:"june",
             7:"july",8:"august",9:"september",10:"october",11:"november",12:"december"}
    slug = f"{POLY_SLUG_BASE}{meses[data_alvo.month]}-{data_alvo.day}-{data_alvo.year}"

    try:
        r = requests.get(f"{GAMMA_API}/events",
            params={"slug": slug}, headers=H_API, timeout=10)
        events = r.json()
        if not events:
            return None, slug

        ev = events[0]
        outcomes = []

        for mkt in ev.get("markets", []):
            q = mkt.get("question", "")
            op = mkt.get("outcomePrices", "")
            try:
                prices = json.loads(op) if isinstance(op, str) else op
                yes_price = float(prices[0])
            except:
                yes_price = 0

            if yes_price < 0.005:
                continue

            # Extrai grau do question
            grau = "?"
            m = re.search(r'be\s+(\d+)\s*°?\s*C', q, re.I)
            if m:
                grau = f"{m.group(1)}°C"
            else:
                m = re.search(r'between\s+(\d+)-(\d+)\s*°?\s*C', q, re.I)
                if m:
                    grau = f"{m.group(1)}-{m.group(2)}°C"
                else:
                    m = re.search(r'(\d+)\s*°?\s*C\s*or\s*(higher|below)', q, re.I)
                    if m:
                        sinal = "≥" if "higher" in m.group(2).lower() else "≤"
                        grau = f"{sinal}{m.group(1)}°C"

            outcomes.append({
                "grau": grau,
                "pct": round(yes_price * 100, 1),
                "question": q,
            })

        outcomes.sort(key=lambda x: x["pct"], reverse=True)
        return outcomes, slug

    except Exception as e:
        print(f"[POLY] Erro: {e}")
        return None, slug


# ═══════════════════════════════════════════
#  FORMATAR MENSAGEM
# ═══════════════════════════════════════════

def c_para_f(c):
    """Celsius → Fahrenheit."""
    return round(c * 9 / 5 + 32, 1)


def formatar_mensagem(temp, outcomes_amanha, slug_amanha, previsao, data_alvo, modelos=None):
    """Monta mensagem completa pro Telegram. TOP 3 sempre do dia seguinte."""
    amanha = date.today() + timedelta(days=1)
    link = f"https://polymarket.com/event/{slug_amanha}" if slug_amanha else ""

    msg = "🇰🇷 <b>SEOUL — Temperatura</b>\n"
    msg += f"📅 Hoje: {data_alvo.strftime('%d/%m/%Y')}\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    # Temperatura atual — °C e °F
    if temp.get("atual"):
        c = temp["atual"]
        f = c_para_f(c)
        msg += f"🌡️ <b>Agora: {c}°C / {f}°F</b> (Wunderground RKSI)\n"
    if temp.get("max"):
        c_max = temp["max"]
        c_min = temp.get("min", "?")
        f_max = c_para_f(c_max) if isinstance(c_max, (int, float)) else "?"
        f_min = c_para_f(c_min) if isinstance(c_min, (int, float)) else "?"
        msg += f"📈 Máxima hoje: <b>{c_max}°C ({f_max}°F)</b> | Mínima: {c_min}°C ({f_min}°F)\n"
    msg += "\n"

    # Modelos para AMANHÃ
    if modelos and modelos.get("media"):
        amanha_dt = datetime.strptime(modelos["data"], "%Y-%m-%d")
        msg += f"🔮 <b>PREVISÃO AMANHÃ ({amanha_dt.strftime('%d/%m')}):</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        if modelos.get("ecmwf"):
            ec = modelos["ecmwf"]
            msg += f"  🇪🇺 ECMWF: <b>{ec}°C ({c_para_f(ec)}°F)</b>\n"
        if modelos.get("gfs"):
            gf = modelos["gfs"]
            msg += f"  🇺🇸 GFS: <b>{gf}°C ({c_para_f(gf)}°F)</b>\n"
        if modelos.get("best"):
            bm = modelos["best"]
            msg += f"  🌐 Best Match: <b>{bm}°C ({c_para_f(bm)}°F)</b>\n"
        med = modelos["media"]
        msg += f"  📊 Média: <b>{med}°C ({c_para_f(med)}°F)</b>\n\n"

    # TOP 3 Polymarket — SEMPRE do dia seguinte
    if outcomes_amanha:
        msg += f"📊 <b>TOP 3 Polymarket ({amanha.strftime('%d/%m')}):</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        for i, o in enumerate(outcomes_amanha[:3], 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉"
            msg += f"{medal} <b>{o['grau']}</b> → <b>{o['pct']}%</b>\n"
        msg += "\n"

        msg += "📋 <b>Todas as opções:</b>\n"
        for o in outcomes_amanha:
            bar = "█" * int(o["pct"] / 5) + "░" * (20 - int(o["pct"] / 5))
            msg += f"  {o['grau']:<8} {bar} {o['pct']}%\n"
        msg += "\n"

    # Previsão 5 dias — °C e °F
    if previsao:
        msg += "📅 <b>Previsão 5 dias (Seoul):</b>\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        for p in previsao[:5]:
            mx, mn = p["max"], p["min"]
            msg += f"  {p['data']} → 🔺{mx}°C ({c_para_f(mx)}°F)  🔻{mn}°C ({c_para_f(mn)}°F)\n"
        msg += "\n"

    if link:
        msg += f"🔗 <a href=\"{link}\">Polymarket Amanhã</a>\n"
    msg += f"📡 <a href=\"https://www.wunderground.com/weather/kr/incheon/RKSI\">Wunderground RKSI</a>"

    return msg


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════

# ═══════════════════════════════════════════
#  MONITORAMENTO — busca temp a cada 10s via Open-Meteo (sem cache)
# ═══════════════════════════════════════════

def buscar_temp_atual_rapido():
    """Busca temperatura ATUAL via Open-Meteo — rápido, sem Selenium, sem cache."""
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast",
            params={"latitude": 37.46, "longitude": 126.44,
                    "current": "temperature_2m",
                    "timezone": "Asia/Seoul"},
            headers={"Cache-Control": "no-cache"},
            timeout=8)
        d = r.json().get("current", {})
        return d.get("temperature_2m"), d.get("time", "")
    except:
        return None, ""


def executar_completo():
    """Varredura completa: WU + Polymarket AMANHÃ + previsão + modelos."""
    print(f"\n{'='*50}")
    print(f"  VARREDURA COMPLETA {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*50}")

    hoje = date.today()
    amanha = hoje + timedelta(days=1)

    print("[1] Buscando temperatura Wunderground...")
    temp = buscar_temp_wunderground()

    print(f"[2] Buscando Polymarket Seoul AMANHÃ ({amanha.strftime('%d/%m')})...")
    outcomes_amanha, slug_amanha = buscar_polymarket_seoul(amanha)
    if outcomes_amanha:
        top3 = [o["grau"] + "=" + str(o["pct"]) + "%" for o in outcomes_amanha[:3]]
        print(f"    Top 3: {', '.join(top3)}")

    print("[3] Buscando previsão 5 dias...")
    previsao = buscar_previsao_5dias()
    if previsao:
        dias = [p["data"] + ":" + str(p["max"]) + "°C" for p in previsao[:5]]
        print(f"    {', '.join(dias)}")

    print("[4] Buscando ECMWF + GFS para amanhã...")
    modelos = buscar_modelos_amanha()

    msg = formatar_mensagem(temp, outcomes_amanha, slug_amanha, previsao, hoje, modelos)
    enviar(msg)
    print("[OK] Varredura completa enviada!")

    return outcomes_amanha, slug_amanha


def main():
    print("╔══════════════════════════════════════════╗")
    print("║  SEOUL WEATHER BOT — Monitor Tempo Real  ║")
    print("║  Selenium + Open-Meteo + Polymarket      ║")
    print("║  Monitora a cada 10s, envia se mudou     ║")
    print("╚══════════════════════════════════════════╝")

    enviar(
        "🤖 <b>Seoul Weather Bot Ativo!</b>\n\n"
        "📡 Wunderground RKSI (Selenium)\n"
        "📊 Polymarket Seoul\n"
        "�🇺 ECMWF + 🇺🇸 GFS\n\n"
        "⚡ Monitora a cada 10s\n"
        "📩 Envia quando temperatura muda"
    )

    # Varredura completa inicial
    outcomes, slug = executar_completo()

    ultima_temp = None
    ciclo = 0

    while True:
        try:
            time.sleep(10)
            ciclo += 1

            # Busca temperatura atual (rápido, sem Selenium)
            temp_agora, hora_str = buscar_temp_atual_rapido()

            if temp_agora is None:
                continue

            temp_arredondada = round(temp_agora, 1)

            # Se mudou → envia alerta
            if temp_arredondada != ultima_temp:
                hora = hora_str.split("T")[1][:5] if "T" in hora_str else "?"
                direcao = ""
                if ultima_temp is not None:
                    diff = temp_arredondada - ultima_temp
                    if diff > 0:
                        direcao = f" ⬆️ +{diff:.1f}°C"
                    elif diff < 0:
                        direcao = f" ⬇️ {diff:.1f}°C"

                print(f"[🌡️] {temp_arredondada}°C (era {ultima_temp}°C){direcao} — {hora} KST")

                f_agora = c_para_f(temp_arredondada)
                msg = (
                    f"🌡️ <b>Seoul: {temp_arredondada}°C / {f_agora}°F</b>{direcao}\n"
                    f"⏰ {hora} KST (Wunderground RKSI)\n"
                )

                # Mostra top 3 do mercado se disponível
                if outcomes:
                    msg += "\n📊 Polymarket:\n"
                    for o in outcomes[:3]:
                        msg += f"  {o['grau']}: {o['pct']}%\n"

                if slug:
                    msg += f"\n🔗 <a href=\"https://polymarket.com/event/{slug}\">Mercado</a>"

                enviar(msg)
                ultima_temp = temp_arredondada

            # A cada 5 min (30 ciclos) → varredura completa
            if ciclo % 30 == 0:
                outcomes, slug = executar_completo()

            # Log a cada 60s
            if ciclo % 6 == 0:
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] {temp_arredondada}°C (sem mudança)")

        except KeyboardInterrupt:
            print("\n[INFO] Encerrado.")
            break
        except Exception as e:
            print(f"[ERRO] {e}")
            time.sleep(10)


if __name__ == "__main__":
    main()
