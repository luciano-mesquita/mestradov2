import time
import json
import os
import board
import busio
import adafruit_ads1x15.ads1115 as ADS
from adafruit_ads1x15.analog_in import AnalogIn

# Configuração de Hardware
i2c = busio.I2C(board.SCL, board.SDA)
ads = ADS.ADS1115(i2c)
ads.gain = 2/3 
chan = AnalogIn(ads, ADS.P0)

CONFIG_PATH = "configs.json"

def carregar_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            return json.load(f)
    return {
        "cilindroAr": 0.03135,
        "alturaCilindro": 0.05,
        "diametroCilindro": 0.05,
        "pressaoAtmosferica": 95000,
        "offset": 0.0,
        "v_fonte": 4.965,
        "tempoCalculoOffset": 5
    }

def calcular_offset_ultra_robusto(tempo_estabilizacao=5):
    """Super Auto-Zero: ~500 amostras com descarte de 20% de outliers."""
    print(f"--- INICIANDO CALIBRAÇÃO (TARA) DE {tempo_estabilizacao}s ---")
    print("Sistema em repouso. Aguarde a estabilização térmica...")
    
    amostras = []
    tempo_final = time.time() + tempo_estabilizacao
    
    while time.time() < tempo_final:
        amostras.append(chan.voltage)
        time.sleep(0.01) 
    
    total = len(amostras)
    amostras.sort()
    
    # Corte estatístico para eliminar picos de interferência na calibração
    corte = total // 10
    amostras_filtradas = amostras[corte:-corte]
    
    v_medio = sum(amostras_filtradas) / len(amostras_filtradas)
    
    desvio = max(amostras_filtradas) - min(amostras_filtradas)
    print(f"Concluído. Estabilidade: {desvio:.5f} V | Zero: {v_medio:.4f} V")
    return round(v_medio, 6)

def ajustar_offset():
    config = carregar_config()
    tempo_offset = float(config.get("tempoCalculoOffset", 5))
    novo_offset = calcular_offset_ultra_robusto(tempo_offset)

    config["offset"] = novo_offset
    config["v_fonte"] = 4.965 
    
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=4)

    try:
        from hardware.sensor import atualizar_config_global
        atualizar_config_global()
    except Exception as e:
        print(f"Aviso: não foi possível atualizar cache do sensor em RAM: {e}")
    
    print(f"Ponto zero atualizado com sucesso no arquivo de configurações.")

if __name__ == "__main__":
    ajustar_offset()
