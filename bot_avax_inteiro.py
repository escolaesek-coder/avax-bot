from binance.client import Client
from binance.exceptions import BinanceAPIException
import time
import os
import math

# ============================
# CONFIGURAÇÕES GERAIS
# ============================

API_KEY = os.getenv("BINANCE_API_KEY")
API_SECRET = os.getenv("BINANCE_API_SECRET")

if not API_KEY or not API_SECRET:
    raise RuntimeError(
        "Defina BINANCE_API_KEY e BINANCE_API_SECRET nas variáveis de ambiente."
    )

client = Client(API_KEY, API_SECRET)

SYMBOL = "AVAXUSDT"

VALOR_USDT_POR_TRADE = 1.0  # compra cerca de 1 USDT em avax
MIN_LEVEL = 10              # compra só se o inteiro estiver entre 10...
MAX_LEVEL = 148             # ...e 148
INTERVALO_SEGUNDOS = 5      

EPS = 1e-6  # tolerância para comparar floats

# ============================
# VARIÁVEIS DE ESTADO
# ============================

in_position = False
entry_level = None
buy_price = None
qty_posicao = None

# ============================
# BUSCAR REGRAS DO PAR
# ============================

def pegar_symbol_info(symbol: str):
    info = client.get_symbol_info(symbol)
    if info is None:
        raise RuntimeError(f"Não foi possível obter info do símbolo {symbol}.")
    return info

def pegar_step_size_e_min_notional(symbol: str):
    info = pegar_symbol_info(symbol)
    step_size = 0.001
    min_notional = 0.0

    for f in info["filters"]:
        if f["filterType"] == "LOT_SIZE":
            step_size = float(f["stepSize"])
        if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL"):
            min_notional = float(f.get("minNotional", f.get("notional", 0.0)))

    return step_size, min_notional

STEP_SIZE, MIN_NOTIONAL = pegar_step_size_e_min_notional(SYMBOL)

print(f"StepSize: {STEP_SIZE}")
print(f"Valor mínimo por ordem (MinNotional): {MIN_NOTIONAL} USDT")

# ============================
# FUNÇÕES AUXILIARES
# ============================

def pegar_preco_atual(symbol: str) -> float:
    ticker = client.get_symbol_ticker(symbol=symbol)
    return float(ticker["price"])

def preco_e_inteiro(preco: float) -> bool:
    return abs(preco - round(preco)) < EPS

def arredondar_quantidade(qty: float, step: float) -> float:
    if qty <= 0:
        return 0.0
    steps = math.floor(qty / step)
    return steps * step

def calcular_quantidade_avax(preco_atual: float) -> float:
    valor_alvo = max(VALOR_USDT_POR_TRADE, MIN_NOTIONAL)
    qty_bruta = valor_alvo / preco_atual
    qty_ajustada = arredondar_quantidade(qty_bruta, STEP_SIZE)
    return qty_ajustada

def enviar_ordem_mercado(symbol: str, side: str, quantity: float):
    try:
        ordem = client.order_market(symbol=symbol, side=side, quantity=quantity)
        print(f"ORDEN ENVIADA: {side} {quantity} {symbol}")
        print(ordem)
        return ordem
    except Exception as e:
        print("Erro ao enviar ordem:", e)
        return None

def calcular_preco_medio(ordem: dict) -> float:
    fills = ordem.get("fills", [])
    if not fills:
        return float(ordem.get("price", 0.0))

    total_valor = 0.0
    total_qty = 0.0
    for f in fills:
        p = float(f["price"])
        q = float(f["qty"])
        total_valor += p * q
        total_qty += q

    return total_valor / total_qty if total_qty > 0 else 0.0

def log_estado():
    if in_position:
        print(f"POSIÇÃO ABERTA | nível {entry_level} | preço médio {buy_price} | qty {qty_posicao}")
    else:
        print("SEM POSIÇÃO ABERTA.")

# ============================
# LOOP PRINCIPAL
# ============================

def loop_bot():
    global in_position, entry_level, buy_price, qty_posicao

    print("BOT AVAX INICIADO (opera apenas em preços inteiros)")

    while True:
        try:
            preco = pegar_preco_atual(SYMBOL)
            print(f"\nPreço atual: {preco}")

            # ======================
            # SEM POSIÇÃO → COMPRA
            # ======================
            if not in_position:

                if not preco_e_inteiro(preco):
                    print("Aguardando preço ser inteiro...")
                    log_estado()
                    time.sleep(INTERVALO_SEGUNDOS)
                    continue

                level = int(round(preco))

                if level < MIN_LEVEL or level > MAX_LEVEL:
                    print(f"Nível {level} fora do intervalo permitido.")
                    time.sleep(INTERVALO_SEGUNDOS)
                    continue

                qty = calcular_quantidade_avax(preco)
                if qty <= 0:
                    print("Quantidade insuficiente.")
                    time.sleep(INTERVALO_SEGUNDOS)
                    continue

                print(f"COMPRA detectada no nível {level}, qty {qty}")
                ordem = enviar_ordem_mercado(SYMBOL, "BUY", qty)
                if ordem is None:
                    continue

                qty_exec = float(ordem["executedQty"])
                preco_medio = calcular_preco_medio(ordem)

                in_position = True
                entry_level = level
                buy_price = preco_medio
                qty_posicao = qty_exec

                print(f"COMPRA CONFIRMADA | nível {entry_level} | preço médio {buy_price}")

            # ======================
            # COM POSIÇÃO → VENDA
            # ======================
            else:
                target = entry_level + 1
                print(f"Aguardando VENDA no preço inteiro {target}.")

                if preco_e_inteiro(preco) and int(round(preco)) == target:

                    print(f"VENDA detectada no nível {target}")
                    ordem_venda = enviar_ordem_mercado(SYMBOL, "SELL", qty_posicao)
                    if ordem_venda is None:
                        continue

                    preco_medio_venda = calcular_preco_medio(ordem_venda)

                    lucro = (preco_medio_venda - buy_price) * qty_posicao

                    print(f"VENDA CONFIRMADA | preço {preco_medio_venda} | lucro {lucro}")

                    # Zerar posição
                    in_position = False
                    entry_level = None
                    buy_price = None
                    qty_posicao = None

            log_estado()
            time.sleep(INTERVALO_SEGUNDOS)

        except KeyboardInterrupt:
            print("Bot encerrado pelo usuário.")
            break
        except Exception as e:
            print("Erro no loop principal:", e)
            time.sleep(5)

# ============================
# INICIAR BOT
# ============================

if __name__ == "__main__":
    loop_bot()
