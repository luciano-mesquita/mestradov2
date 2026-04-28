import RPi.GPIO as GPIO
import time
import os
import json
import statistics

CONFIG_PATH = "configs.json"
CONFIG_DEFAULTS = {
    "cilindroAr": 0.03135,
    "alturaCilindro": 0.05,
    "diametroCilindro": 0.05,
    "pressaoAtmosferica": 95000,
    "offset": 1.1615,
    "v_fonte": 4.965,
    "pressaoCalibracaoMaxima": 1000,
    "pressaoInicialMedicao": 1100,
    "pressaoFinalMedicao": 0,
    "modoCompressorCalibracao": "intervalado",
    "tempoIntervaloCompressor": 0.3,
    "tempoEsvaziamentoCilindro": 5,
    "casasDecimaisDisplay": 2,
    "tempoCalculoOffset": 5
}

def garantir_dependencias():
    """Valida módulos necessários para aquisição I2C."""
    try:
        import board  # noqa: F401
        import busio  # noqa: F401
        import adafruit_ads1x15.ads1115 as ADS  # noqa: F401
        _ = statistics.median([1, 2, 3])
    except Exception as e:
        print(f"Aviso de dependências de hardware: {e}")

def garantir_config_padrao():
    """Cria/atualiza configs.json com campos essenciais."""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                atual = json.load(f)
        except Exception:
            atual = {}
    else:
        atual = {}

    alterado = False
    for chave, valor in CONFIG_DEFAULTS.items():
        if chave not in atual:
            atual[chave] = valor
            alterado = True

    if alterado or not os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump(atual, f, indent=4)

# Função para configurar os pinos do compressor e solenoide
def configurar_hardware():
    garantir_dependencias()
    garantir_config_padrao()

    # Configuração do pino GPIO para controlar o compressor e a solenoide
    GPIO.setmode(GPIO.BCM)
    
    # Defina os pinos dos dispositivos
    rele_compressor_pin = 17  # Pino GPIO para o compressor
    rele_solenoide_pin = 18   # Pino GPIO para a solenoide

    # Configura os pinos como saída
    GPIO.setup(rele_compressor_pin, GPIO.OUT)
    GPIO.setup(rele_solenoide_pin, GPIO.OUT)

    # Inicializa os pinos em HIGH para desligar o compressor e a solenoide
    GPIO.output(rele_compressor_pin, GPIO.HIGH)  # Compressor desligado
    GPIO.output(rele_solenoide_pin, GPIO.HIGH)   # Solenoide desligada

    print("Compressor e solenoide inicializados desligados.")
    
# Função para limpar a configuração dos pinos GPIO
def limpar_gpio():
    GPIO.cleanup()  # Limpa as configurações de GPIO

if __name__ == "__main__":
    configurar_hardware()  # Chama a função para configurar o hardware
    try:
        # Qualquer lógica do seu sistema pode vir aqui
        pass
    finally:
        limpar_gpio()  # Garante que os pinos sejam limpos no final
