import time
import json
import os
import RPi.GPIO as GPIO
from hardware.sensor import get_pressure  # Usamos get_pressure para obter a pressão com o offset carregado de configs.json

# Configuração do pino GPIO para controlar o relé do mini compressor
rele_pin = 17  # Pino GPIO para controlar o relé do mini compressor
ESTABILIZACAO_RELE = 0.2
CONFIG_PATH = "configs.json"

def _carregar_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"pressaoCalibracaoMaxima": 1000}

def _garantir_gpio_configurado():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(rele_pin, GPIO.OUT)

# Função para ativar o mini compressor
def ativar_compressor():
    """Ativa o mini compressor (abre o relé)."""
    _garantir_gpio_configurado()
    print("Ativando o mini compressor...")
    GPIO.output(rele_pin, GPIO.LOW)  # Envia sinal LOW para ligar o compressor (relé fechado)
    time.sleep(ESTABILIZACAO_RELE)
    print("Compressor ativado.")

# Função para desativar o mini compressor
def desativar_compressor():
    """Desativa o mini compressor (fecha o relé)."""
    _garantir_gpio_configurado()
    print("Desligando o mini compressor...")
    GPIO.output(rele_pin, GPIO.HIGH)  # Envia sinal HIGH para desligar o compressor (relé aberto)
    time.sleep(ESTABILIZACAO_RELE)
    print("Compressor desativado.")

# Função para calibrar o cilindro até atingir 1000 Pa
def calibrar_cilindro(tempo_maximo=120):
    """Calibra cilindro até a pressão configurada com modo direto ou intervalado."""
    print("Iniciando calibração do cilindro...")
    config = _carregar_config()
    pressao_calibracao = float(config.get("pressaoCalibracaoMaxima", 1000))
    modo_compressor = str(config.get("modoCompressorCalibracao", "intervalado")).lower()
    tempo_intervalo = max(0.05, float(config.get("tempoIntervaloCompressor", 0.3)))
    inicio = time.time()

    try:
        compressor_ligado = False
        while True:
            if time.time() - inicio > tempo_maximo:
                raise TimeoutError(
                    f"Tempo máximo excedido na calibração ({tempo_maximo}s). "
                    f"Pressão-alvo: {pressao_calibracao} Pa."
                )

            try:
                pressao = get_pressure()  # Lê a pressão do sensor (em Pa)
            except Exception as e:
                print(f"Falha momentânea na leitura de pressão: {e}")
                desativar_compressor()
                time.sleep(0.2)
                continue

            print(f"Pressão Atual: {pressao} Pa")

            if pressao >= pressao_calibracao:
                desativar_compressor()
                print(f"Pressão calibrada. Alvo de {pressao_calibracao} Pa atingido.")
                break

            if modo_compressor == "direto":
                if not compressor_ligado:
                    print("Modo compressor: direto.")
                    ativar_compressor()
                    compressor_ligado = True
                time.sleep(0.1)
            else:
                # Aciona em pulsos para evitar overshoot e travamentos
                print(f"Modo compressor: intervalado ({tempo_intervalo:.2f}s).")
                ativar_compressor()
                time.sleep(tempo_intervalo)
                desativar_compressor()
                compressor_ligado = False
                time.sleep(tempo_intervalo)
    finally:
        # Garantia de segurança: compressor sempre desligado ao sair
        desativar_compressor()
