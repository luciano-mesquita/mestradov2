from flask import Flask, render_template, request, jsonify, send_file
from hardware.sensor import get_pressure
from datetime import datetime
from threading import Thread, Lock
import time
import os
import subprocess
from odf.opendocument import OpenDocumentSpreadsheet, load
from odf.table import Table, TableRow, TableCell
from odf.text import P
import json
import math
from scipy.stats import linregress
from hardware.compressor import calibrar_cilindro
from hardware.offset import ajustar_offset
from hardware.solenoide import esvaziar_cilindro, abrir_solenoide, fechar_solenoide
from hardware.setup import configurar_hardware, limpar_gpio

limpar_gpio()
configurar_hardware()

app = Flask(__name__)

dados_medicao = []
medindo = False
parar_automatico = False
dados_auto_salvos = False
planilha_nome = ""
metadados = {}  # <-- metadados adicionados
lock = Lock()
feedback_sistema = {
    "mensagem": "Sistema pronto.",
    "nivel": "info",
    "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
}
feedback_lock = Lock()

def registrar_feedback(mensagem, nivel="info"):
    global feedback_sistema
    with feedback_lock:
        feedback_sistema = {
            "mensagem": mensagem,
            "nivel": nivel,
            "atualizado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    print(f"[{nivel.upper()}] {mensagem}")

def ler_pressao_segura(tentativas=3, atraso=0.1):
    """Lê pressão com tolerância a falhas transitórias do I2C."""
    ultimo_erro = None
    for _ in range(tentativas):
        try:
            return get_pressure()
        except Exception as e:
            ultimo_erro = e
            time.sleep(atraso)
    raise RuntimeError(f"Falha na leitura do ADS1115: {ultimo_erro}")

def aguardar_estabilizacao_pressao(automacao_cancelada):
    """
    Aguarda a estabilização da pressão para iniciar a medição automática.
    Critérios:
    - Pressão deve estar dentro da faixa [min, max] durante a janela.
    - Oscilação na janela (max - min) deve ser <= variação configurada.
    """
    config = carregar_config()
    pressao_min = float(config.get("pressaoAutoMinima", 995))
    pressao_max = float(config.get("pressaoAutoMaxima", 1005))
    janela_s = max(1, int(float(config.get("janelaLeituraEstabilizacao", 5))))
    variacao_pa = float(config.get("variacaoEstabilizacaoPa", 5))
    timeout_s = max(1, int(float(config.get("timeoutEstabilizacao", 30))))

    registrar_feedback(
        f"Aguardando estabilização ({pressao_min:.1f}–{pressao_max:.1f} Pa, janela {janela_s}s, variação ≤ {variacao_pa:.1f} Pa).",
        "info"
    )

    inicio_espera = time.time()
    leituras = []

    while True:
        if automacao_cancelada():
            return False, "Medição automática cancelada durante estabilização."

        if time.time() - inicio_espera > timeout_s:
            return False, (
                f"Timeout de estabilização atingido ({timeout_s}s). "
                f"Não foi possível atingir a faixa {pressao_min:.1f}–{pressao_max:.1f} Pa."
            )

        pressao = ler_pressao_segura()
        agora = time.time()
        leituras.append((agora, pressao))

        limite_tempo = agora - janela_s
        leituras = [(t, p) for t, p in leituras if t >= limite_tempo]

        if len(leituras) < janela_s:
            time.sleep(1)
            continue

        valores = [p for _, p in leituras]
        todos_na_faixa = all(pressao_min <= p <= pressao_max for p in valores)
        oscilacao = max(valores) - min(valores)

        if todos_na_faixa and oscilacao <= variacao_pa:
            return True, (
                f"Pressão estabilizada na faixa {pressao_min:.1f}–{pressao_max:.1f} Pa "
                f"com oscilação de {oscilacao:.1f} Pa em {janela_s}s."
            )

        time.sleep(1)

@app.route("/")
def index():
    return render_template("index.html")

# Rota para obter a pressão
@app.route("/get_pressure")
def get_pressure_route():
    # Função que retorna a pressão atual do sensor (em Pa)
    try:
        pressao = ler_pressao_segura()
        return jsonify({"pressao": pressao})
    except Exception as e:
        return jsonify({"erro": str(e)}), 503

@app.route("/status")
def status_sistema():
    with feedback_lock:
        return jsonify(feedback_sistema)

# Rota para ajustar o offset e salvar no arquivo
@app.route("/ajustar_offset", methods=["POST"])
def ajustar_offset_flask():
    """Rota para ajustar o offset e salvar no arquivo 'configs.json'."""
    try:
        registrar_feedback("Ajustando offset do sensor...", "info")
        ajustar_offset()  # Chama a função que ajusta e salva o offset
        registrar_feedback("Offset ajustado com sucesso.", "success")
        return jsonify({"status": "Offset ajustado e salvo com sucesso!"})
    except Exception as e:
        registrar_feedback(f"Erro ao ajustar offset: {str(e)}", "error")
        return jsonify({"status": f"Erro ao ajustar o offset: {str(e)}"}), 500

@app.route("/start", methods=["POST"])
def start():
    global medindo, dados_medicao, planilha_nome, metadados

    if medindo:
        return jsonify({"status": "já em execução"})

    req = request.get_json()
    planilha_nome = req.get("planilha", "log_pressao.ods")
    if not planilha_nome.endswith(".ods"):
        planilha_nome += ".ods"

    metadados = {
        "Responsável": req.get("responsavel", ""),
        "Coordenadas": req.get("coordenadas", ""),
        "Descrição": req.get("descricao", ""),
        "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    dados_medicao = []
    try:
        pressao_inicial_cilindro = ler_pressao_segura()
        with lock:
            dados_medicao.append({
                "tempo": 1,
                "pressao": pressao_inicial_cilindro
            })

        medindo = True
        registrar_feedback("Medição manual iniciada. Abrindo solenóide...", "info")
        abrir_solenoide()
        registrar_feedback("Solenóide aberta. Coletando pressão manualmente.", "success")
    except Exception as e:
        medindo = False
        registrar_feedback(f"Falha ao abrir solenóide na medição manual: {e}", "error")
        return jsonify({"status": f"Erro ao abrir a solenóide no início da medição manual: {e}"}), 500

    def medir():
        tempo = 2
        while medindo:
            inicio_ciclo = time.perf_counter()
            try:
                pressao = ler_pressao_segura()
            except Exception as e:
                print(f"Erro de leitura na medição manual: {e}")
                time.sleep(0.2)
                continue
            with lock:
                dados_medicao.append({
                    "tempo": tempo,
                    "pressao": pressao
                })
                tempo += 1
            elapsed = time.perf_counter() - inicio_ciclo
            time.sleep(max(0, 1 - elapsed))

    Thread(target=medir).start()
    return jsonify({"status": "medição iniciada"})

@app.route("/start_auto", methods=["POST"])
def start_auto():
    global medindo, dados_medicao, planilha_nome, metadados, parar_automatico, dados_auto_salvos

    if medindo:
        return jsonify({"status": "já em execução"})

    req = request.get_json()
    planilha_nome = req.get("planilha", "log_pressao.ods")
    if not planilha_nome.endswith(".ods"):
        planilha_nome += ".ods"

    metadados = {
        "Responsável": req.get("responsavel", ""),
        "Coordenadas": req.get("coordenadas", ""),
        "Descrição": req.get("descricao", ""),
        "Data": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    dados_medicao = []
    parar_automatico = False
    dados_auto_salvos = False
    registrar_feedback("Medição automática iniciada. Preparando sequência...", "info")
    
    def sequencia_automatica():
        global medindo, parar_automatico, dados_auto_salvos
        try:
            def automacao_cancelada():
                return parar_automatico

            # Abrir solenoide por 3 segundos para limpar/estabilizar
            if automacao_cancelada():
                return
            registrar_feedback("Esvaziando cilindro...", "info")
            esvaziar_cilindro()
            print("Esvaziando cilindro...")

            # Pequena pausa para estabilizar a pressão
            print("Estabilizando pressão...")
            time.sleep(2)
            if automacao_cancelada():
                return

            registrar_feedback("Usando offset atual em RAM para medição automática.", "info")
            
            print("Estabilizando pressão...")
            # Pequena pausa para estabilizar a pressão
            time.sleep(2)
            if automacao_cancelada():
                return

            # Calibra cilindro até 1000 Pa
            print("Calibrando cilindro...")
            registrar_feedback("Calibrando cilindro para pressão alvo...", "info")
            calibrar_cilindro() 
            if automacao_cancelada():
                return
            
            # Pequena pausa para estabilizar a pressão antes de soltar
            print("Estabilizando pressão...")
            time.sleep(2)
            if automacao_cancelada():
                return

            estabilizado, mensagem_estabilizacao = aguardar_estabilizacao_pressao(automacao_cancelada)
            if not estabilizado:
                registrar_feedback(mensagem_estabilizacao, "error")
                medindo = False
                try:
                    fechar_solenoide()
                except Exception:
                    pass
                return
            registrar_feedback(mensagem_estabilizacao, "success")

            # 3. Iniciar a Medição (Captura de dados)
            print("Iniciando medição...")
            registrar_feedback("Iniciando medição automática e abrindo solenóide...", "info")
            medindo = True
            pressao_inicial_cilindro = ler_pressao_segura()
            with lock:
                dados_medicao.append({"tempo": 1, "pressao": pressao_inicial_cilindro})
            # Abrir solenoide aqui para começar o esvaziamento medido
            print("abrindo solenóide...")
            abrir_solenoide() 
            
            tempo = 2
            while medindo and not automacao_cancelada():
                inicio_ciclo = time.perf_counter()
                try:
                    pressao = ler_pressao_segura()
                except Exception as e:
                    print(f"Erro de leitura na medição automática: {e}")
                    time.sleep(0.2)
                    continue
                config = carregar_config()
                pressao_max_estabilizacao = float(config.get("pressaoAutoMaxima", 1005))
                pressao_final = float(config.get("pressaoFinalMedicao", 0))

                # Registra continuamente para evitar "travamento visual" quando a pressão
                # ultrapassa momentaneamente o valor inicial configurado.
                with lock:
                    dados_medicao.append({"tempo": tempo, "pressao": pressao})
                tempo += 1
                
                # Condição de parada automática: só considera fim após sair da faixa de calibração
                # e retornar ao limiar final.
                if pressao <= pressao_final and pressao <= pressao_max_estabilizacao:
                    medindo = False

                elapsed = time.perf_counter() - inicio_ciclo
                time.sleep(max(0, 1 - elapsed))

            # 4. Finalização
            print("Fechando solenóide...")
            fechar_solenoide()
            registrar_feedback("Medição automática finalizada. Solenóide fechada.", "success")
            
            with lock:
                if dados_medicao and not dados_auto_salvos:
                    k = calcular_permeabilidade(dados_medicao)
                    salvar_em_aba(dados_medicao, planilha_nome, permeabilidade=k)
                    dados_auto_salvos = True
            
            print("Automação concluída com sucesso.")

        except Exception as e:
            print(f"Erro na automação: {e}")
            registrar_feedback(f"Erro na automação: {e}", "error")
            medindo = False

    # Inicia todo o processo em uma Thread separada
    Thread(target=sequencia_automatica).start()
    return jsonify({"status": "Automação iniciada"})

def calcular_permeabilidade(dados):
    if len(dados) < 2:
        return None  # não há dados suficientes

    tempos = [d["tempo"] for d in dados if d["pressao"] > 0]
    pressoes = [d["pressao"] for d in dados if d["pressao"] > 0]
    ln_pressoes = [math.log(p) for p in pressoes]

    if len(tempos) != len(ln_pressoes):
        return None

    # Regressão linear ln(P) vs. t
    slope, intercept, *_ = linregress(tempos, ln_pressoes)

    # Carrega configurações
    config = carregar_config()
    altura = float(config["alturaCilindro"])
    diametro = float(config["diametroCilindro"])
    volume = float(config["cilindroAr"])
    pressao_atm = float(config["pressaoAtmosferica"])

    # Área da seção transversal
    area = math.pi * (diametro ** 2) / 4
    viscosidade_ar = 1.81e-5  # Pa·s

    # Fórmula da permeabilidade
    k = (2.3 * altura * viscosidade_ar * volume) / (area * pressao_atm) * abs(slope)
    return k

# Rota para iniciar a calibração do cilindro até atingir 1000 Pa
@app.route("/calibrar_cilindro", methods=["POST"])
def calibrar_cilindro_flask():
    """Rota para iniciar a calibração do cilindro até 1000 Pa"""
    # Inicia a calibração em uma thread separada para não bloquear o servidor Flask
    registrar_feedback("Calibração do cilindro iniciada.", "info")
    Thread(target=calibrar_cilindro).start()
    return jsonify({"status": "Calibração iniciada. O compressor será ativado até atingir 1000 Pa."})

# Rota para abrir válvula solenóide
@app.route("/esvaziar_cilindro", methods=["POST"])
def esvaziar_cilindro_flask():
    registrar_feedback("Esvaziamento do cilindro iniciado.", "info")
    Thread(target=esvaziar_cilindro).start()
    return jsonify({"status": "Cilindro esvaziado."})

@app.route("/restart_service", methods=["POST"])
def restart_service():
    try:
        subprocess.run(["service", "permeametro", "restart"], check=True)
        return jsonify({"status": "Serviço reiniciado com sucesso."})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": f"Erro ao reiniciar o serviço: {str(e)}"}), 500

@app.route("/shutdown", methods=["POST"])
def shutdown():
    try:
        subprocess.run(["shutdown", "-h", "now"], check=True)
        return jsonify({"status": "Desligamento iniciado."})
    except subprocess.CalledProcessError as e:
        return jsonify({"status": f"Erro ao desligar o sistema: {str(e)}"}), 500

@app.route("/stop", methods=["POST"])
def stop():
    global medindo
    if not medindo:
        return jsonify({"status": "nenhuma medição em andamento"})

    medindo = False
    time.sleep(1)
    try:
        fechar_solenoide()
        registrar_feedback("Medição manual finalizada. Solenóide fechada.", "success")
    except Exception as e:
        registrar_feedback(f"Medição manual finalizada, mas houve falha ao fechar solenóide: {e}", "warning")
        print(f"Falha ao fechar solenóide na medição manual: {e}")

    with lock:
        k = calcular_permeabilidade(dados_medicao)
        salvar_em_aba(dados_medicao, planilha_nome, permeabilidade=k)

    return jsonify({"status": "medição finalizada e planilha salva"})

@app.route("/stop_auto", methods=["POST"])
def stop_auto():
    global medindo, parar_automatico, dados_auto_salvos
    parar_automatico = True
    medindo = False
    try:
        fechar_solenoide()
        registrar_feedback("Parada manual da medição automática solicitada.", "warning")
    except Exception:
        pass
    
    with lock:
        if dados_medicao and not dados_auto_salvos:
            k = calcular_permeabilidade(dados_medicao)
            salvar_em_aba(dados_medicao, planilha_nome, permeabilidade=k)
            dados_auto_salvos = True

    return jsonify({"status": "Parada da medição automática solicitada."})

@app.route("/data")
def data():
    with lock:
        return jsonify(dados_medicao)

@app.route("/planilhas")
def listar_planilhas():
    arquivos = [f for f in os.listdir('.') if f.endswith(".ods")]
    return jsonify(arquivos)

@app.route("/download/<nome>")
def download_planilha(nome):
    caminho = os.path.join('.', nome)
    if os.path.exists(caminho):
        return send_file(caminho, as_attachment=True)
    return "Arquivo não encontrado", 404

def salvar_em_aba(dados, arquivo, permeabilidade=None):
    if os.path.exists(arquivo):
        doc = load(arquivo)
    else:
        doc = OpenDocumentSpreadsheet()

    nome_aba = "Medição " + datetime.now().strftime("%H:%M:%S")
    table = Table(name=nome_aba)

    # Metadados
    for chave, valor in metadados.items():
        row = TableRow()
        cell_key = TableCell()
        cell_key.addElement(P(text=f"{chave}:"))
        cell_val = TableCell()
        cell_val.addElement(P(text=str(valor)))
        row.addElement(cell_key)
        row.addElement(cell_val)
        table.addElement(row)

    # Linha em branco
    table.addElement(TableRow())

    # Cabeçalho
    header = TableRow()
    for col in ["Tempo (s)", "Pressão (Pa)"]:
        cell = TableCell()
        cell.addElement(P(text=col))
        header.addElement(cell)
    table.addElement(header)

    # Dados
    dados_validos = [d for d in dados if d["pressao"] != 0]
    for row_data in dados_validos:
        row = TableRow()
        for val in [row_data["tempo"], row_data["pressao"]]:
            cell = TableCell()
            cell = TableCell(valuetype="float", value=val)
            row.addElement(cell)
        table.addElement(row)

    # Valor calculado pelo Python
    if permeabilidade is not None:
        # Linha com valor calculado pelo Python
        # row = TableRow()
        # cell_label = TableCell()
        # cell_label.addElement(P(text="Permeabilidade (m²) [Python]:"))
        # cell_val = TableCell()
        # cell_val.addElement(P(text=str(permeabilidade).replace('.', ',')))
        # row.addElement(cell_label)
        # row.addElement(cell_val)
        # table.addElement(row)

        # Linha com fórmula para LibreOffice Calc
        row_formula = TableRow()
        cell_label_formula = TableCell()
        cell_label_formula.addElement(P(text="Permeabilidade (m²)"))

        linha_inicial = 7
        linha_final = len(dados_validos) + 6  # Ex: dados com 10 linhas => linha_final = 16

        formula = (
            'of:=((2.3 * 0.05 * 0.0000181 * 0.03135) / ((PI() * 0.05^2 / 4) * 95000)) * '
            f'ABS(SLOPE(LN([.B{linha_inicial}:.B{linha_final}]); [.A{linha_inicial}:.A{linha_final}]))'
        )

        cell_formula = TableCell(formula=formula, valuetype="float")
        cell_formula.addElement(P(text=""))
        row_formula.addElement(cell_label_formula)
        row_formula.addElement(cell_formula)
        table.addElement(row_formula)

    doc.spreadsheet.addElement(table)
    doc.save(arquivo)
    print(f"Planilha salva: {arquivo}")

CONFIG_PATH = "configs.json"

def salvar_config(config):
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f)

def carregar_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r') as f:
            config = json.load(f)
    else:
        config = {
            "cilindroAr": 0.03135,
            "alturaCilindro": 0.05,
            "diametroCilindro": 0.05,
            "pressaoAtmosferica": 95000
        }

    config.setdefault("offset", 1.1615)
    config.setdefault("v_fonte", 4.965)
    config.setdefault("cilindroAr", 0.03135)
    config.setdefault("alturaCilindro", 0.05)
    config.setdefault("diametroCilindro", 0.05)
    config.setdefault("pressaoAtmosferica", 95000)
    config.setdefault("pressaoCalibracaoMaxima", 1000)
    config.setdefault("pressaoFinalMedicao", 0)
    config.setdefault("pressaoAutoMinima", 995)
    config.setdefault("pressaoAutoMaxima", 1005)
    config.setdefault("janelaLeituraEstabilizacao", 5)
    config.setdefault("variacaoEstabilizacaoPa", 5)
    config.setdefault("timeoutEstabilizacao", 30)
    config.setdefault("modoCompressorCalibracao", "intervalado")
    config.setdefault("tempoIntervaloCompressor", 0.3)
    config.setdefault("tempoEsvaziamentoCilindro", 5)
    config.setdefault("casasDecimaisDisplay", 2)
    config.setdefault("tempoCalculoOffset", 5)
    return config

@app.route("/config", methods=["POST"])
def configurar_equipamento():
    config_atual = carregar_config()
    novo_config = request.get_json() or {}
    config_atual.update(novo_config)
    salvar_config(config_atual)
    return jsonify({"status": "Configuração salva com sucesso"})

@app.route("/config", methods=["GET"])
def obter_configuracoes():
    config = carregar_config()
    return jsonify(config)

@app.route("/relatorios")
def relatorios():
    arquivos = [f for f in os.listdir('.') if f.endswith(".ods")]
    return render_template("relatorios.html", arquivos=arquivos)

from odf.opendocument import load
from odf.table import Table

@app.route("/relatorios/abas/<arquivo>")
def listar_abas(arquivo):
    try:
        doc = load(arquivo)
        abas = [table.getAttribute("name") for table in doc.spreadsheet.getElementsByType(Table)]
        return jsonify(abas)
    except Exception as e:
        return jsonify({"erro": str(e)}), 500

from odf.table import TableRow, TableCell
from odf.text import P

@app.route("/relatorios/dados", methods=["POST"])
def dados_aba():
    req = request.get_json()
    arquivo = req.get("arquivo")
    aba = req.get("aba")

    doc = load(arquivo)
    for table in doc.spreadsheet.getElementsByType(Table):
        if table.getAttribute("name") == aba:
            rows = []
            for row in table.getElementsByType(TableRow):
                cells = []
                for cell in row.getElementsByType(TableCell):
                    ps = cell.getElementsByType(P)
                    text = "".join([p.firstChild.data if p.firstChild else "" for p in ps])
                    cells.append(text)
                rows.append(cells)
            return jsonify(rows)
    return jsonify([])

# if __name__ == "__main__":
#     app.run(debug=False, use_reloader=False)

if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
