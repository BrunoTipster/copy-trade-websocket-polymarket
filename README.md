# 🚨 Copy Trade Bot — Polymarket → Telegram

Bot que monitora **20+ wallets de top traders** da Polymarket em tempo real e envia sinais no Telegram quando eles fazem operações.

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 📸 Exemplo de Sinal no Telegram

```
🟢 COMPROU — Polymarket
👤 Poligarch (#8 +$25k)
🎯 Mercado: A temperatura mais alta em Tóquio será de 22°C em 16 de abril?
➡️ Apostou no: Sim
📊 Chance: 32.0%

💰 Preço: $0.32
📦 Quantidade: 11.59 shares
💵 Valor: $3.71
🕐 15/04 15:31:24

🔗 Ver mercado
🔍 Polygonscan
```

```
🏆 WIN — Polymarket
👤 HondaCivic (#3 +$32k)
🎯 Mercado: A temperatura mais alta em Miami estará entre 74-75°F (23.3-23.9°C)?
📌 Resultado: Sim

💰 Entrada: $298.85
💵 Recebeu: $304.14
📈 Lucro/Prejuízo: $5.29
```

---

## ⚡ Arquitetura

O bot usa uma **arquitetura híbrida** para máxima velocidade:

```
┌─────────────────────────────────────────────────┐
│              WebSocket (tempo real)              │
│  wss://ws-subscriptions-clob.polymarket.com     │
│  Canal: market → escuta last_trade_price        │
│  Detecta: "alguém negociou nesse mercado"       │
└──────────────────────┬──────────────────────────┘
                       │ trigger
                       ▼
┌─────────────────────────────────────────────────┐
│              REST API (detalhes)                 │
│  https://data-api.polymarket.com/trades         │
│  Busca: quem fez, quanto, em qual mercado       │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────┐
│              Telegram Bot API                    │
│  Formata mensagem em português                  │
│  Traduz mercado (Google Translate gratuito)      │
│  Converte °F → °C automaticamente               │
│  Envia sinal com links clicáveis                │
└─────────────────────────────────────────────────┘
```

### Por que híbrido?

- **WebSocket sozinho** não diz *quem* fez a trade, só que aconteceu
- **REST sozinho** tem delay de 5-10s por ciclo de polling
- **Híbrido**: WS detecta em ~1s que houve trade → REST busca os detalhes → latência total de **1-3 segundos**

---

## 🔧 Como Funciona (Passo a Passo)

### 1. Warmup (Inicialização)
Ao iniciar, o bot carrega os últimos 50 trades de cada wallet monitorada e marca como "já vistos". Isso evita enviar sinais de trades antigos.

### 2. WebSocket — Detecção em Tempo Real
Conecta no canal `market` da Polymarket e assina os `asset_ids` das posições abertas dos traders. Quando recebe um evento `last_trade_price`, sabe que alguém negociou naquele mercado.

### 3. REST Polling — Busca de Detalhes
Quando o WebSocket dispara, ou a cada 8 segundos como fallback, o bot consulta a Data API para cada wallet:
```
GET https://data-api.polymarket.com/trades?user=<wallet>&limit=20
```
Compara com trades já enviados (por `transactionHash`) e processa os novos.

### 4. Tradução Automática
Usa a API gratuita do Google Translate (`translate.googleapis.com`) para traduzir o nome do mercado e o outcome para português. Tem cache para não traduzir a mesma frase duas vezes.

### 5. Conversão °F → °C
Detecta automaticamente temperaturas em Fahrenheit no texto e adiciona o equivalente em Celsius:
- `74-75°F` → `74-75°F (23.3-23.9°C)`
- `90°F` → `90°F (32.2°C)`

### 6. Detecção de WIN/LOSS
A cada 30 segundos, consulta a Activity API para detectar redemptions (quando um mercado resolve e o trader recebe USDC). Calcula lucro/prejuízo comparando com o preço de entrada.

### 7. Heartbeat
Envia `PING` a cada 10 segundos para manter a conexão WebSocket viva (requisito da Polymarket).

---

## 👥 Wallets Monitoradas

| Trader | Categoria | PnL Mensal |
|--------|-----------|------------|
| Handsanitizer23 | Clima | +$74k |
| ColdMath | Clima | #2 |
| HondaCivic | Clima | +$32k |
| Maskache2 | Clima | +$31k |
| BeefSlayer | Clima | +$28k |
| Poligarch | Clima | +$25k |
| Kyrgyzhydromet | Clima | +$23k |
| Lavincey | Clima | +$22k |
| dpnd | Clima | +$18k |
| JoeTheMeteorologist | Clima | +$17k |
| speeda | Clima | +$20k |
| Bruno | Principal + Proxy | — |
| gopfan / gopfan2 | Clima + Política | — |
| aenews2 | Política | — |
| LucasMeow | Geral | — |

---

## 🚀 Instalação e Uso

### Requisitos
- Python 3.10+
- Bibliotecas: `requests`, `websocket-client`

### Setup

```bash
# Clone o repositório
git clone https://github.com/BrunoTipster/copy-trade-websocket-polymarket.git
cd copy-trade-websocket-polymarket

# Instale as dependências
pip install requests websocket-client
```

### Configuração

Edite as variáveis no topo do `bot.py`:

```python
TELEGRAM_TOKEN   = "SEU_TOKEN_AQUI"
TELEGRAM_CHAT_ID = "SEU_CHAT_ID_AQUI"
```

Para adicionar/remover wallets, edite o dicionário `WALLETS`:

```python
WALLETS = {
    "0xENDERECO": "Nome do Trader",
    # ...
}
```

### Rodar

```bash
python bot.py
```

Output esperado:
```
Iniciando bot...
====================================================
  POLYMARKET COPY TRADE BOT  (WS + REST)
  Wallets: 20 | Polling: 8s
====================================================
[INFO] Carregando trades existentes...
[OK] 847 trades | 52 posições | 89 assets para WS
[WS] Thread iniciada
[WS] Conectado → wss://ws-subscriptions-clob.polymarket.com/ws/market
[WS] Subscrito em 89 assets existentes
[OK] Bot pronto!
[WS] Trade detectada! asset=1157301638248847... price=0.86
[WS] 3 asset(s) com trade detectado → verificando wallets...
[NOVO] BeefSlayer (#5 +$28k): BUY Will the highest... — $85.00
```

---

## 📡 APIs Utilizadas

| API | URL | Auth | Uso |
|-----|-----|------|-----|
| Data API | `data-api.polymarket.com` | Não | Trades e activities por wallet |
| WebSocket | `ws-subscriptions-clob.polymarket.com` | Não | Detecção em tempo real |
| Google Translate | `translate.googleapis.com` | Não | Tradução EN→PT |
| Telegram Bot | `api.telegram.org` | Token | Envio de mensagens |

---

## ⚙️ Configurações

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `INTERVALO_REST` | `8` | Segundos entre cada ciclo de polling REST |
| `MIN_VALOR` | `1.0` | Ignora trades abaixo desse valor em USD |
| `WS_URL` | `wss://...` | URL do WebSocket da Polymarket |

---

## 📁 Estrutura

```
.
├── bot.py          # Código completo (arquivo único)
├── README.md       # Esta documentação
├── .gitignore
└── requirements.txt
```

Arquivo único por design — sem dependências complexas, sem múltiplos módulos. Fácil de entender, modificar e rodar.

---

## ⚠️ Disclaimer

Este bot é apenas para **monitoramento e alertas**. Não executa trades automaticamente. Qualquer decisão de investimento é de sua responsabilidade. Mercados de previsão envolvem risco financeiro.

---

## 📄 Licença

MIT
