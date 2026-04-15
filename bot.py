"""
Copy Trade Bot - Polymarket → Telegram
Arquitetura híbrida: WebSocket (detecção) + REST (detalhes)

Fluxo:
  1. Warmup REST: carrega trades existentes de todas as wallets
  2. REST polling leve (30s) como fallback
  3. WebSocket market channel: assina os asset_ids das posições abertas
     → quando detecta last_trade_price, dispara verificação REST imediata
  4. Envia sinal no Telegram com todos os detalhes
"""

import sys
import os
import requests
import time
import threading
import json
import websocket  # pip install websocket-client
from datetime import datetime

# Força output imediato no terminal
os.environ["PYTHONUNBUFFERED"] = "1"

# ═══════════════════════════════════════════
#  CONFIGURAÇÕES
# ═══════════════════════════════════════════

TELEGRAM_TOKEN   = "8744601987:AAFVTdhf2qyDE-OgooIesuHMd9PmhBGSIqo"
TELEGRAM_CHAT_ID = "-1003910452966"

INTERVALO_REST   = 8    # segundos entre polling REST completo
MIN_VALOR        = 1.0  # ignora trades abaixo de $X
MIN_CHANCE       = 5.0  # ignora trades com chance abaixo de X% (filtra spray/lixo)
MIN_CHANCE_NO    = 5.0  # mínimo para apostas "No" também

WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

DATA_API    = "https://data-api.polymarket.com"
HEADERS     = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

WALLETS = {
    "0xf2f6af4f27ec2dcf4072095ab804016e14cd5817": "gopfan2 - CLIMA (#19)",
    "0x44c1dfe43260c94ed4f1d00de2e1f80fb113ebc1": "aenews2 - POLÍTICA",
    "0x6af75d4e4aaf700450efbac3708cce1665810ff1": "gopfan - CLIMA",
    "0x594edb9112f526fa6a80b8f858a6379c8a2c1c11": "ColdMath (#2)",
    "0xe5c8026239919339b988fdb150a7ef4ea196d3e7": "Anon-e5c8",
    "0xee00ba338c59557141789b127927a55f5cc5cea1": "Anon-ee00",
    "0x7f3c8979d0afa00007bae4747d5347122af05613": "LucasMeow",
    "0xd3c55d67859f9e7102fe22f8ddf3b0c89170728f": "Bruno (principal)",
    "0x1abbac62c40a33c91ed607307692182773f73020": "Bruno (proxy)",
    "0x05e70727a2e2dcd079baa2ef1c0b88af06bb9641": "Handsanitizer23 (#1 +$74k)",
    "0x15ceffed7bf820cd2d90f90ea24ae9909f5cd5fa": "HondaCivic (#3 +$32k)",
    "0x1f66796b45581868376365aef54b51eb84184c8d": "Maskache2 (#4 +$31k)",
    "0x331bf91c132af9d921e1908ca0979363fc47193f": "BeefSlayer (#5 +$28k)",
    "0xb40e89677d59665d5188541ad860450a6e2a7cc9": "Poligarch (#8 +$25k)",
    "0xf1faf3f6ad1e0264d6cbecc1a416e7c536be047d": "Kyrgyzhydromet (#9 +$23k)",
    "0x1cdd071bb612de6d66d0c882b676c663697de595": "Lavincey (#10 +$22k)",
    "0x1838cca016850ac7185a9b149fe7d0bd2d6629b4": "JoeTheMeteorologist (#16 +$17k)",
    "0x5f211a24da4c005d9438a1ea269673b85ed0b376": "dpnd (#15 +$18k)",
    "0x43cb4ae1f4ddc9e671486c79c9f40a6fd98b84df": "Trader #13 (+$20k)",
    "0x46745788e678a6f8ceebcd8bc7e37462b74703ca": "speeda (#14 +$20k)",
}

# ═══════════════════════════════════════════
#  ESTADO GLOBAL
# ═══════════════════════════════════════════

trades_enviados    = set()   # tx hashes já enviados
activities_enviadas = set()  # redemptions já enviadas
posicoes_abertas   = {}      # conditionId → {wallet, outcome, price, size, ...}
asset_ids_ativos   = set()   # asset_ids das posições abertas (para WS)

# Fila de asset_ids que o WS sinalizou como "teve trade agora"
ws_triggered       = set()
ws_lock            = threading.Lock()

# WebSocket app global
ws_app = None


# ═══════════════════════════════════════════
#  TELEGRAM
# ═══════════════════════════════════════════

def enviar(msg):
    for attempt in range(3):
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": msg,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
                timeout=10,
            )
            data = r.json()
            if data.get("ok"):
                return True
            retry = data.get("parameters", {}).get("retry_after", 0)
            if retry:
                time.sleep(retry + 1)
                continue
            # Fallback sem HTML
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": msg},
                timeout=10,
            )
            return True
        except Exception as e:
            print(f"[ERRO] Telegram: {e}")
            time.sleep(2)
    return False


# ═══════════════════════════════════════════
#  API POLYMARKET
# ═══════════════════════════════════════════

def buscar_trades(wallet, limit=20):
    try:
        r = requests.get(
            f"{DATA_API}/trades",
            params={"user": wallet, "limit": limit},
            headers=HEADERS, timeout=15,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[ERRO] trades {wallet[:10]}: {e}")
        return []


def buscar_activities(wallet, limit=20):
    try:
        r = requests.get(
            f"{DATA_API}/activity",
            params={"user": wallet, "limit": limit},
            headers=HEADERS, timeout=15,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as e:
        print(f"[ERRO] activity {wallet[:10]}: {e}")
        return []


# ═══════════════════════════════════════════
#  TRADUÇÃO (Google Translate gratuito via requests)
# ═══════════════════════════════════════════

_cache_trad = {}


def f_para_c(f):
    """Converte Fahrenheit para Celsius."""
    return round((f - 32) * 5 / 9, 1)


import re

def adicionar_celsius(texto):
    """Detecta temperaturas em °F e adiciona °C ao lado. Ex: 74-75°F → 74-75°F (23.3-23.9°C)"""
    # Padrão: 74-75°F ou 74°F
    def substituir_range(m):
        f1 = float(m.group(1))
        f2 = float(m.group(2))
        c1 = f_para_c(f1)
        c2 = f_para_c(f2)
        return f"{int(f1)}-{int(f2)}°F ({c1}-{c2}°C)"

    def substituir_single(m):
        f = float(m.group(1))
        c = f_para_c(f)
        return f"{int(f)}°F ({c}°C)"

    # Range: 74-75°F ou 74-75 °F ou 74-75F
    texto = re.sub(r'(\d+)-(\d+)\s*°?\s*F\b', substituir_range, texto)
    # Single: 90°F ou 90 °F ou 90F
    texto = re.sub(r'(\d+)\s*°?\s*F\b', substituir_single, texto)
    return texto

def traduzir(texto):
    """Traduz inglês → português usando API gratuita do Google Translate."""
    if not texto or texto in ("?", "Yes", "No"):
        return {"Yes": "Sim", "No": "Não"}.get(texto, texto)
    if texto in _cache_trad:
        return _cache_trad[texto]
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "pt", "dt": "t", "q": texto},
            timeout=5,
        )
        result = r.json()[0]
        trad = "".join(part[0] for part in result if part[0])
        _cache_trad[texto] = trad
        return trad
    except Exception:
        return texto


# ═══════════════════════════════════════════
#  FORMATAÇÃO
# ═══════════════════════════════════════════

def formatar_trade(t, nome):
    side    = t.get("side", "?")
    title   = t.get("title", "?")
    outcome = t.get("outcome", "?")
    price   = float(t.get("price", 0))
    size    = float(t.get("size", 0))
    slug    = t.get("eventSlug", "")
    ts      = t.get("timestamp", 0)
    tx      = t.get("transactionHash", "")
    cid     = t.get("conditionId", "")
    valor   = round(price * size, 2)
    prob    = round(price * 100, 1)
    dt      = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M:%S") if ts else "?"

    emoji = "\U0001f7e2" if side == "BUY" else "\U0001f534"
    acao  = "COMPROU" if side == "BUY" else "VENDEU (SAIU)"
    link  = f"https://polymarket.com/event/{slug}" if slug else ""

    msg = (
        f"{emoji} <b>{acao}</b> — Polymarket\n"
        f"\U0001f464 <b>{nome}</b>\n"
        f"\U0001f3af Mercado: <b>{adicionar_celsius(traduzir(title))}</b>\n"
        f"\u27a1\ufe0f Apostou no: <b>{traduzir(outcome)}</b>\n"
        f"\U0001f4ca Chance: <b>{prob}%</b>\n\n"
        f"\U0001f4b0 Preço: ${price}\n"
        f"\U0001f4e6 Quantidade: <b>{size:.2f} shares</b>\n"
        f"\U0001f4b5 Valor: <b>${valor}</b>\n"
    )

    # Se SELL, mostra lucro/prejuízo comparando com entrada
    if side == "SELL" and cid and cid in posicoes_abertas:
        pos = posicoes_abertas[cid]
        preco_entrada = float(pos.get("price", 0))
        if preco_entrada > 0:
            lucro_por_share = price - preco_entrada
            lucro_total = round(lucro_por_share * size, 2)
            pct = round((lucro_por_share / preco_entrada) * 100, 1)
            if lucro_total >= 0:
                msg += f"\n\U0001f4c8 <b>LUCRO: +${lucro_total} (+{pct}%)</b>\n"
                msg += f"\U0001f4b2 Entrada: ${preco_entrada} → Saída: ${price}\n"
            else:
                msg += f"\n\U0001f4c9 <b>PREJUÍZO: ${lucro_total} ({pct}%)</b>\n"
                msg += f"\U0001f4b2 Entrada: ${preco_entrada} → Saída: ${price}\n"

    msg += f"\U0001f552 {dt}\n"

    if link:
        msg += f"\n\U0001f517 <a href=\"{link}\">Ver mercado</a>"
    if tx:
        msg += f"\n\U0001f50d <a href=\"https://polygonscan.com/tx/{tx}\">Polygonscan</a>"
    return msg


def formatar_resultado(a, nome, pos):
    title   = a.get("title", "?")
    outcome = a.get("outcome", "?")
    usdc    = float(a.get("usdcSize", 0))
    ts      = a.get("timestamp", 0)
    slug    = a.get("eventSlug", "")
    dt      = datetime.fromtimestamp(ts).strftime("%d/%m %H:%M:%S") if ts else "?"
    custo   = round(float(pos.get("price", 0)) * float(pos.get("size", 0)), 2)

    if usdc > 0 and custo > 0:
        lucro = round(usdc - custo, 2)
        emoji, resultado = ("\U0001f3c6", "WIN") if lucro >= 0 else ("\U0001f4a5", "LOSS")
    elif usdc > 0:
        emoji, resultado, lucro = "\U0001f3c6", "WIN", round(usdc, 2)
    else:
        emoji, resultado, lucro = "\U0001f4a5", "LOSS", 0

    link = f"https://polymarket.com/event/{slug}" if slug else ""
    msg = (
        f"{emoji} <b>{resultado}</b> — Polymarket\n"
        f"\U0001f464 <b>{nome}</b>\n"
        f"\U0001f3af Mercado: <b>{adicionar_celsius(traduzir(title))}</b>\n"
        f"\U0001f4cc Resultado: <b>{traduzir(outcome)}</b>\n\n"
    )
    if custo > 0:
        msg += f"\U0001f4b0 Entrada: <b>${custo}</b>\n"
    msg += (
        f"\U0001f4b5 Recebeu: <b>${round(usdc, 2)}</b>\n"
        f"\U0001f4c8 Lucro/Prejuízo: <b>${lucro}</b>\n"
        f"\U0001f552 {dt}\n"
    )
    if link:
        msg += f"\n\U0001f517 <a href=\"{link}\">Ver mercado</a>"
    return msg, resultado, lucro


# ═══════════════════════════════════════════
#  PROCESSAMENTO DE TRADES
# ═══════════════════════════════════════════

def processar_trades_wallet(wallet, nome):
    """Busca e processa trades novos de uma wallet."""
    trades = buscar_trades(wallet)
    for t in trades:
        tx = t.get("transactionHash", "")
        if not tx or tx in trades_enviados:
            continue
        trades_enviados.add(tx)

        price = float(t.get("price", 0))
        size  = float(t.get("size", 0))
        if price * size < MIN_VALOR:
            continue

        # Filtro inteligente: ignora apostas de spray/lixo
        chance = price * 100
        outcome = (t.get("outcome") or "").lower()
        side = t.get("side", "?")

        if side == "BUY" and outcome == "yes" and chance < MIN_CHANCE:
            # Apostou SIM em algo com menos de 5% de chance = spray
            print(f"[FILTRO] {nome}: BUY Yes {chance:.1f}% (< {MIN_CHANCE}%) — ignorado")
            continue

        if side == "BUY" and outcome == "no":
            # Apostou NÃO = está apostando contra. Chance do "No" = price
            chance_no = price * 100
            if chance_no < MIN_CHANCE_NO:
                print(f"[FILTRO] {nome}: BUY No {chance_no:.1f}% — ignorado")
                continue

        msg = formatar_trade(t, nome)
        side  = t.get("side", "?")
        title = (t.get("title") or "?")[:50]
        print(f"[NOVO] {nome}: {side} {title} — ${price*size:.2f}")
        enviar(msg)

        if side == "BUY":
            cid = t.get("conditionId", "")
            aid = t.get("asset", "")
            if cid:
                posicoes_abertas[cid] = {
                    "wallet": wallet, "nome": nome,
                    "outcome": t.get("outcome"),
                    "price": price, "size": size,
                    "title": t.get("title"),
                    "slug": t.get("eventSlug"),
                }
            # Adiciona asset_id ao WS
            if aid:
                asset_ids_ativos.add(aid)
                ws_subscribe([aid])

        time.sleep(0.3)


def checar_resultados():
    """Checa redemptions (WIN/LOSS) de todas as wallets."""
    for wallet, nome in WALLETS.items():
        for a in buscar_activities(wallet):
            tx   = a.get("transactionHash", "")
            tipo = (a.get("type") or "").upper()
            if "REDEEM" not in tipo or not tx or tx in activities_enviadas:
                continue
            activities_enviadas.add(tx)
            cid = a.get("conditionId", "")
            pos = posicoes_abertas.get(cid, {})
            msg, resultado, lucro = formatar_resultado(a, nome, pos)
            print(f"[{resultado}] {nome}: {a.get('title','?')} → ${lucro}")
            enviar(msg)
            posicoes_abertas.pop(cid, None)
        time.sleep(0.05)


# ═══════════════════════════════════════════
#  WEBSOCKET
# ═══════════════════════════════════════════

def ws_subscribe(asset_ids):
    """Envia mensagem de subscribe para novos asset_ids."""
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
        print(f"[WS] Subscrito em {len(asset_ids)} asset(s)")
    except Exception as e:
        print(f"[WS] Erro subscribe: {e}")


def on_ws_message(ws, message):
    """Processa mensagens do WebSocket."""
    global ws_triggered
    try:
        if message in ("PONG", "pong"):
            return

        data = json.loads(message)

        # Pode vir como lista ou dict
        events = data if isinstance(data, list) else [data]

        for event in events:
            etype = event.get("event_type") or event.get("type") or ""

            # last_trade_price = alguém acabou de fazer uma trade nesse mercado
            if etype == "last_trade_price":
                asset_id = event.get("asset_id", "")
                price    = event.get("price", "?")
                print(f"[WS] Trade detectada! asset={asset_id[:16]}... price={price}")
                with ws_lock:
                    ws_triggered.add(asset_id)

    except Exception as e:
        print(f"[WS] Erro parse: {e}")


def on_ws_open(ws):
    global ws_app
    ws_app = ws
    print(f"[WS] Conectado → {WS_URL}")

    # Subscreve nos asset_ids já conhecidos
    if asset_ids_ativos:
        msg = json.dumps({
            "assets_ids": list(asset_ids_ativos),
            "type": "market",
            "custom_feature_enabled": True,
        })
        ws.send(msg)
        print(f"[WS] Subscrito em {len(asset_ids_ativos)} assets existentes")
    else:
        # Sem assets ainda, manda mensagem vazia para não ser desconectado
        ws.send(json.dumps({"type": "market", "assets_ids": [], "custom_feature_enabled": True}))


def on_ws_error(ws, error):
    print(f"[WS] Erro: {error}")


def on_ws_close(ws, code, msg):
    print(f"[WS] Desconectado (code={code}). Reconectando em 5s...")
    time.sleep(5)
    iniciar_websocket()


def heartbeat_loop(ws):
    """Envia PING a cada 10s para manter conexão viva."""
    while True:
        time.sleep(10)
        try:
            if ws and ws.sock and ws.sock.connected:
                ws.send("PING")
        except Exception:
            break


def iniciar_websocket():
    """Inicia WebSocket em thread separada."""
    def run():
        app = websocket.WebSocketApp(
            WS_URL,
            on_open=on_ws_open,
            on_message=on_ws_message,
            on_error=on_ws_error,
            on_close=on_ws_close,
        )
        # Inicia heartbeat em thread separada
        hb = threading.Thread(target=heartbeat_loop, args=(app,), daemon=True)
        hb.start()
        app.run_forever(ping_interval=0)  # ping manual via heartbeat

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print("[WS] Thread iniciada")


# ═══════════════════════════════════════════
#  WARMUP
# ═══════════════════════════════════════════

def warmup():
    print("[INFO] Carregando trades existentes...")
    total = 0
    for wallet, nome in WALLETS.items():
        trades = buscar_trades(wallet, limit=50)
        for t in trades:
            tx = t.get("transactionHash", "")
            if tx:
                trades_enviados.add(tx)
                total += 1
            if t.get("side") == "BUY":
                cid = t.get("conditionId", "")
                aid = t.get("asset", "")
                if cid:
                    posicoes_abertas[cid] = {
                        "wallet": wallet, "nome": nome,
                        "outcome": t.get("outcome"),
                        "price": t.get("price", 0),
                        "size": t.get("size", 0),
                        "title": t.get("title"),
                        "slug": t.get("eventSlug"),
                    }
                if aid:
                    asset_ids_ativos.add(aid)

        for a in buscar_activities(wallet, limit=50):
            tx = a.get("transactionHash", "")
            if tx:
                activities_enviadas.add(tx)

        time.sleep(0.1)

    print(f"[OK] {total} trades | {len(posicoes_abertas)} posições | {len(asset_ids_ativos)} assets para WS")


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════

def main():
    print("=" * 52)
    print("  POLYMARKET COPY TRADE BOT  (WS + REST)")
    print(f"  Wallets: {len(WALLETS)} | Polling: {INTERVALO_REST}s")
    print("=" * 52)

    # 1. Warmup
    warmup()

    # 2. Inicia WebSocket
    iniciar_websocket()
    time.sleep(2)  # aguarda conexão

    # 3. Startup Telegram
    nomes = "\n".join(f"  • {n}" for n in WALLETS.values())
    enviar(
        f"\U0001f916 <b>Copy Trade Bot Ativo!</b>\n\n"
        f"Monitorando <b>{len(WALLETS)}</b> wallets:\n{nomes}\n\n"
        f"\u26a1 WebSocket ativo\n"
        f"\u23f1 Polling REST: {INTERVALO_REST}s"
    )
    print(f"[OK] Bot pronto!")

    ciclo = 0
    while True:
        time.sleep(INTERVALO_REST)
        ciclo += 1

        # ── WS trigger: verifica wallets cujos assets tiveram trade ──
        triggered = set()
        with ws_lock:
            triggered = ws_triggered.copy()
            ws_triggered.clear()

        if triggered:
            print(f"[WS] {len(triggered)} asset(s) com trade detectado → verificando wallets...")
            # Descobre quais wallets têm posição nesses assets
            wallets_para_checar = set()
            for cid, pos in posicoes_abertas.items():
                wallets_para_checar.add((pos["wallet"], pos["nome"]))
            # Também checa todas (o WS não diz quem fez, só que houve trade)
            for wallet, nome in WALLETS.items():
                processar_trades_wallet(wallet, nome)
        else:
            # ── REST polling normal ──
            for wallet, nome in WALLETS.items():
                processar_trades_wallet(wallet, nome)
                time.sleep(0.05)

        # A cada 30s checa WIN/LOSS
        if ciclo % (30 // INTERVALO_REST) == 0:
            checar_resultados()

        # Log periódico
        if ciclo % 60 == 0:
            print(f"[INFO] Ciclo {ciclo} | Trades: {len(trades_enviados)} | "
                  f"Posições: {len(posicoes_abertas)} | WS assets: {len(asset_ids_ativos)}")


if __name__ == "__main__":
    print("Iniciando bot...", flush=True)
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Bot encerrado.")
    except Exception as e:
        import traceback
        print(f"[FATAL] {e}", flush=True)
        traceback.print_exc()
