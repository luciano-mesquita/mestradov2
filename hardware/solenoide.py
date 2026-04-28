import time
import json
import os
import RPi.GPIO as GPIO
from hardware.sensor import get_pressure  # Para acessar a leitura de pressão

# Configuração do pino GPIO para controlar a válvula solenoide
solenoide_pin = 18  # Pino GPIO que controla a válvula solenoide (ajuste conforme necessário)
ESTABILIZACAO_RELE = 0.2
CONFIG_PATH = "configs.json"

def _carregar_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"tempoEsvaziamentoCilindro": 5}

def _garantir_gpio_configurado():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(solenoide_pin, GPIO.OUT)

# Função para abrir a válvula solenoide
def abrir_solenoide():
    """Abre a válvula solenoide para permitir o fluxo de ar"""
    _garantir_gpio_configurado()
    print("Abrindo a válvula solenoide...")
    GPIO.output(solenoide_pin, GPIO.LOW)  # Envia sinal LOW para abrir a válvula
    time.sleep(ESTABILIZACAO_RELE)
    print("Válvula solenoide aberta.")

# Função para fechar a válvula solenoide
def fechar_solenoide():
    """Fecha a válvula solenoide para interromper o fluxo de ar"""
    _garantir_gpio_configurado()
    print("Fechando a válvula solenoide...")
    GPIO.output(solenoide_pin, GPIO.HIGH)  # Envia sinal HIGH para fechar a válvula
    time.sleep(ESTABILIZACAO_RELE)
    print("Válvula solenoide fechada.")

# Função para fechar a válvula solenoide
def esvaziar_cilindro():
    config = _carregar_config()
    tempo_esvaziamento = float(config.get("tempoEsvaziamentoCilindro", 5))
    print("Abrindo a válvula solenoide...")
    abrir_solenoide()
    time.sleep(max(0, tempo_esvaziamento))
    fechar_solenoide()

# Função para controlar a válvula solenoide durante a medição
def controlar_solenoide():
    """Controla a válvula solenoide até que a pressão atinja um valor negativo"""
    while True:
        try:
            pressao = get_pressure()  # Lê a pressão atual do cilindro
        except Exception as e:
            print(f"Falha momentânea na leitura de pressão: {e}")
            time.sleep(0.2)
            continue
        print(f"Pressão atual: {pressao} Pa")

        if pressao > 0:
            # Se a pressão for positiva, abre a válvula solenoide
            abrir_solenoide()
        elif pressao <= 0:
            # Se a pressão for negativa ou zero, fecha a válvula solenoide
            fechar_solenoide()
            break  # Finaliza o processo quando a pressão atingir valor negativo

        time.sleep(1)  # Atualiza a cada 1 segundo
