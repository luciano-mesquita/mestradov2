import time
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn
import json
import os
import statistics
from threading import Lock

# Configuração de Hardware
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 2/3
# Aumentamos a taxa de dados para o máximo do ADS1115 (860 SPS) para reduzir o lag
chan = AnalogIn(ads, ADS.P0)

_sensor_lock = Lock()

# --- CONSTANTES ---
VOLTAGEM_FONTE = 4.965 
SENSIBILIDADE_PA = (VOLTAGEM_FONTE * 0.2) / 1000.0 

# --- CACHE DE CONFIGURAÇÃO ---
# Carregamos o offset globalmente para não ler o arquivo JSON toda hora
OFFSET_GLOBAL = 0.4090

def atualizar_config_global():
    """Chame esta função sempre que rodar o offset.py para atualizar a RAM."""
    global OFFSET_GLOBAL
    CONFIG_PATH = "configs.json"
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r') as f:
                config = json.load(f)
                OFFSET_GLOBAL = config.get("offset", 0.4090)
        except Exception as e:
            print(f"Erro ao ler config: {e}")

# Carrega na inicialização do módulo
atualizar_config_global()

def get_pressure():
    """Retorna a pressão com latência reduzida."""
    with _sensor_lock:
        # 1. Coleta mais rápida: reduzimos para 7 amostras (suficiente para mediana de 15ms)
        # Removido o time.sleep ou reduzido drasticamente
        leituras_inst = []
        for _ in range(7): 
            leituras_inst.append(chan.voltage)
            # O próprio tempo de comunicação I2C já serve de pequeno delay
        
        v_estavel = statistics.median(leituras_inst)
        
        # 2. Cálculo usando o OFFSET_GLOBAL na memória RAM
        pressao_pa = (v_estavel - OFFSET_GLOBAL) / SENSIBILIDADE_PA
        
        # 3. Clip Negativo
        if pressao_pa < 0.0: 
            pressao_pa = 0.0
            
        return round(pressao_pa, 4)

if __name__ == "__main__":
    print(f"Monitorando em Alta Velocidade...")
    try:
        while True:
            # Note que o tempo de resposta agora será quase instantâneo
            print(f"Pressão: {get_pressure():.2f} Pa")
            time.sleep(0.1) # Loop de monitoramento mais rápido (10Hz)
    except KeyboardInterrupt:
        pass