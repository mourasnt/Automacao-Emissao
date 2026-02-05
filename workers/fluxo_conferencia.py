import redis
import json
import time
import datetime
import os
from loguru import logger
from playwright.sync_api import Page
from dados.dataclass import Carga
from fluxos.conferir import conferir_lt
from utils.fluxo_utils import obter_status_lt, garantir_pagina_consulta
from utils.filtros import filtro_cargas
from utils.watchdog import TimeoutDetector 

# Carrega configurações de timeout
config_path = os.path.join(os.path.dirname(__file__), "..", "utils", "config.json")
with open(config_path, "r", encoding="utf-8") as f:
    timeout_config = json.load(f)

PAGE_RELOAD_TIMEOUT = timeout_config.get("timeout_settings", {}).get("page_reload_ms", 45000) 


# --- FUNÇÕES HELPER DE ENVIO DE RESULTADO ---
def enviar_job_update(r_client: redis.Redis, config: dict, row: int, colunas: list, valores: list):
    """Envia um job de ATUALIZAÇÃO para a fila do Writer."""
    try:
        results_queue = config['redis_settings']['results_queue']
        payload = {
            "tipo_job": "UPDATE_SHEET",
            "payload": {
                "row": row,
                "colunas": colunas,
                "novos_valores": valores
            }
        }
        r_client.rpush(results_queue, json.dumps(payload))
        logger.debug(f"[Worker Conferência] Job UPDATE (Linha {row}) enviado ao Writer: {colunas} = {valores}")
    except Exception as e:
        logger.error(f"[Worker Conferência] Falha ao enviar job UPDATE (Linha {row}) para o Redis: {e}")

def enviar_job_append_erro(r_client: redis.Redis, config: dict, numero_lt: str, campo: str, valor: str):
    """Envia um job de ADIÇÃO DE ERRO para a fila do Writer."""
    try:
        results_queue = config['redis_settings']['results_queue']

        # O formato da linha [data, numero_lt, campo, valor] deve bater com sua planilha de erros
        dados_linha_erro = [campo, valor]

        payload = {
            "tipo_job": "APPEND_ERROR_LOG",
            "payload": {
                "dados_linha": dados_linha_erro
            }
        }
        r_client.rpush(results_queue, json.dumps(payload))
        logger.debug(f"[Worker Conferência] Job APPEND (LT {numero_lt}) enviado ao Writer: {campo} -> {valor}")
    except Exception as e:
        logger.error(f"[Worker Conferência] Falha ao enviar job APPEND (LT {numero_lt}) para o Redis: {e}")

# --- FLUXO REATORADO COMO WORKER ---
def fluxo_conferencia_worker(page: Page, config: dict):
    logger.info("[Worker Conferência] Iniciando...")
    
    URL_CONSULTA = "https://portal.emiteai.com.br/#/ecommerce/shopee/consulta"
    SELETOR_CHAVE_CONSULTA = 'button:has-text("Filtrar")'
    
    redis_cfg = config.get('redis_settings', {})
    r_host = redis_cfg.get('host')
    r_port = redis_cfg.get('port')
    r_db = redis_cfg.get('db')
    q_conferencia = redis_cfg.get('conference_queue')
    s_controle = redis_cfg.get('control_set')
    if not s_controle:
        logger.critical(f"[Worker Emissão] Config 'control_set' não encontrada. O Worker não pode limpar o cadeado!")
        return
    
    try:
        from utils.redis_client import get_redis
        r = get_redis(host=r_host, port=r_port, db=r_db)
        logger.info(f"[Worker Conferência] Conectado ao Redis em {r_host}:{r_port}. Ouvindo a fila '{q_conferencia}'")
    except Exception as e:
        logger.critical(f"[Worker Conferência] Não foi possível conectar ao Redis: {e}. Worker encerrando.")
        return

    # Obter watchdog do config (se disponível)
    watchdog = config.get('watchdog', None)
    
    # --- LOOP PRINCIPAL DO WORKER ---
    while True: 
        pagina_esta_ok = garantir_pagina_consulta(
            page=page,
            url_alvo=URL_CONSULTA,
            seletor_chave=SELETOR_CHAVE_CONSULTA
        )
        if not pagina_esta_ok:
            logger.critical("[Worker Conferência] A página de consulta está inacessível. Pausando por 5 minutos.")
            time.sleep(300)
            continue
            
        try:
            resultado_bruto = r.blpop([q_conferencia], timeout=60) 
            
            if resultado_bruto is None:
                logger.debug(f"[Worker Conferência] Nenhum job recebido. Reiniciando loop.")
                continue

            _, job_json = resultado_bruto
            job = json.loads(job_json)
            
            linha_data = job['data']  # Os dados da linha (dicionário)
            linha_num = job['row']    # O número da linha

        except Exception as e:
            logger.error(f"[Worker Conferência] Erro ao obter/decodificar job do Redis: {e}")
            time.sleep(5)
            continue

        # 3. PROCESSAR O JOB
        try:
            numero_lt = (linha_data.get("N° Carga") or "").strip()
            id_job = (linha_data.get("ID 3ZX") or "").strip() or f"{numero_lt}-{linha_num}"
            
            # Registrar job no watchdog
            if watchdog:
                watchdog.registrar_job(numero_lt, worker_id=1, tipo_job="conferencia")
            
            try:
                with TimeoutDetector("Recarregar página", max_seconds=20, job_id=numero_lt):
                    page.reload(wait_until="domcontentloaded", timeout=PAGE_RELOAD_TIMEOUT)
            except Exception as reload_err:
                logger.error(f"[Worker Conferência] Falha ao recarregar página: {reload_err}")
                # Tenta navegar para a página conhecida
                try:
                    with TimeoutDetector("Navegar para consulta", max_seconds=20, job_id=numero_lt):
                        page.goto(URL_CONSULTA, timeout=PAGE_RELOAD_TIMEOUT)
                except Exception as goto_err:
                    logger.error(f"[Worker Conferência] Falha ao navegar para consulta: {goto_err}")
                    continue
            
            carga = Carga.from_row(linha_data)
            data_agora = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            id = (linha_data.get("ID 3ZX") or "").strip() or "LT_DESCONHECIDO"
            numero_lt = (linha_data.get("N° Carga") or "").strip()

            if not carga:
                motivo = "Dados de frete/pedágio inválidos ou ausentes"
                logger.warning(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}) pulado: {motivo}.")
                continue

            if carga.status_emissao != "Pendente":
                motivo = f"Status não é 'Pendente' (é '{carga.status_emissao}')"
                logger.warning(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}) pulado: {motivo}.")
                continue

            if not carga.numero_lt:
                motivo = "Sem número de carga (N° Carga)"
                logger.warning(f"[Worker Conferência] Linha {linha_num} pulada: {motivo}.")
                continue

            status_validos = ["ENTREGA FINALIZADA", "EM TRANSITO", "AGUARDANDO DESCARGA"]
            if carga.status not in status_validos:
                motivo = f"Status '{carga.status}' não requer conferência."
                logger.info(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}) pulado: {motivo}")
                continue

            # --- LÓGICA PRINCIPAL (CAMINHO FELIZ) ---
            logger.info(f"[Worker Conferência] Iniciando RPA para LT {numero_lt} (Linha {linha_num}).")
            
            # Suas funções de RPA
            filtro_cargas(page, carga.numero_lt) # Adicionado de volta
            status_emiteai = obter_status_lt(page, carga.numero_lt)
            logger.info(f"[Worker Conferência] LT {numero_lt}: Status no EmiteAí: {status_emiteai}")
            
            # Prepara o pacote de resultados base
            colunas_update = ["Data Conferência", "Status EmiteAI (coletado)"]
            valores_update = [data_agora, status_emiteai]

            if status_emiteai == "Aguardando Conferência":
                # Chama a sub-tarefa de RPA
                resultado_rpa = conferir_lt(page, carga)
                
                # --- Interpreta o resultado do RPA ---
                if resultado_rpa["status"] == "sucesso":
                    logger.success(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}) SUCESSO na conferência.")
                    # Sucesso! Marcamos para a próxima etapa (Verificar Emissão)
                    colunas_update.append("Status de emissão")
                    valores_update.append("Verificar Emissão")
                
                elif resultado_rpa["status"] == "falha_cadastro":
                    campo_falha = resultado_rpa["campo"]
                    valor_falha = resultado_rpa["valor"]
                    logger.error(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}) FALHOU (Cadastro): {campo_falha} - {valor_falha}")
                    # Envia o log de erro para a outra planilha
                    enviar_job_append_erro(r, config, numero_lt, campo_falha, valor_falha)
                
                elif resultado_rpa["status"] == "falha_rpa":
                    motivo_falha = resultado_rpa.get("motivo") or f"{resultado_rpa.get('campo', 'Erro')}: {resultado_rpa.get('valor', 'Desconhecido')}"
                    logger.error(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}) FALHOU (RPA): {motivo_falha}")

            elif status_emiteai == "Carga Finalizada" or status_emiteai == "Aguardando Emissão":
                colunas_update.append("Status de emissão")
                valores_update.append("Verificar Emissão")
            
            elif status_emiteai == "não encontrado":
                colunas_update.append("Status de emissão")
                valores_update.append("Arquivo c/ Erro")

            else:
                motivo = f"Status EmiteAí '{status_emiteai}' não tratado."
                logger.warning(f"[Worker Conferência] LT {numero_lt} (Linha {linha_num}): {motivo}")

            # 4. ENVIAR RESULTADO (UPDATE) PARA O WRITER
            enviar_job_update(r, config, linha_num, colunas_update, valores_update)

        except Exception as e:
            # 5. LIDAR COM FALHAS INESPERADAS (Ex: o próprio 'obter_status_lt' falhou)
            logger.exception(f"[Worker Conferência] Erro ao processar LT {numero_lt} (Linha {linha_num}).")
            
            continue # Pula para o próximo job
        finally:
            if numero_lt != "LT_DESCONHECIDO" and s_controle:
                try:
                    logger.debug(f"[Worker Conferência] [LT {numero_lt}] Processamento finalizado. Removendo cadeado do '{s_controle}'.")
                    r.srem(s_controle, id)
                except Exception as e_redis:
                    logger.error(f"[Worker Conferência] [LT {numero_lt}] FALHA CRÍTICA ao remover cadeado do '{s_controle}': {e_redis}")
            
            # Finalizar job no watchdog
            if watchdog and numero_lt:
                watchdog.finalizar_job(numero_lt)

    logger.info("[Worker Conferência] Encerrado.")