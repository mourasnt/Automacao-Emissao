import os
import threading
import time
import sys
from playwright.sync_api import sync_playwright # <--- CORREÇÃO: 'Browser' removido
from loguru import logger
from typing import Dict, Any

# --- Imports da sua aplicação ---
try:
    # (Mantendo seu import, assumindo que carregar_config está em helpers)
    from utils.helpers import carregar_config 
except ImportError:
    logger.critical("Não foi possível encontrar 'utils.helpers.carregar_config'.")
    exit(1)

# --- MUDANÇA: Usando seus novos caminhos 'workers/' ---
from workers.fluxo_conferencia import fluxo_conferencia_worker
from workers.fluxo_verificar_emissao import fluxo_verificar_emissao_worker
from fluxos.fluxo_login import fluxo_login
# --- Fim da MUDANÇA ---


# --- Configuração do Logger (Mantida) ---
logger.remove()
# Logs para stdout (Docker)
logger.add(
    sink=sys.stdout, 
    format="{time:DD-MM-YYYY HH:mm:ss} | {level:<7} | [RPA Workers] {message}",
    level="INFO",
    enqueue=True
)
# Logs para arquivo
logger.add(
    "logs/main_rpa.log", 
    rotation="10 MB", 
    retention="5 days", 
    level="DEBUG",
    format="{time:DD-MM-YYYY HH:mm:ss} | {level:<7} | {file}:{line} | {message}",
    enqueue=True
)


USUARIO = os.environ.get('RPA_USUARIO', "35036755820")
SENHA = os.environ.get('RPA_SENHA', "120487@Ka")

if not USUARIO or not SENHA:
    logger.critical("Variáveis RPA_USUARIO/RPA_SENHA não configuradas. Defina-as no ambiente.")
    exit(1)

# ===================================================================
# FUNÇÃO DE EXECUÇÃO DE FLUXO (Alvo da Thread - CORRIGIDA)
# ===================================================================
def executar_fluxo(nome_fluxo: str, funcao_fluxo, config: Dict[str, Any]): # <--- CORREÇÃO: 'browser' removido
    """
    Executa um único worker de automação em seu próprio contexto E
    em sua própria instância do Playwright.
    """
    context = None
    browser = None 
    
    # --- CORREÇÃO: O 'with' do Playwright vem PARA DENTRO da thread ---
    with sync_playwright() as playwright:
        try:
            logger.info(f"Iniciando thread e navegador para o worker: '{nome_fluxo}'")
            
            browser = playwright.firefox.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://portal.emiteai.com.br/#/login")

            login_ok = fluxo_login(page=page, usuario=USUARIO, senha=SENHA)
            if not login_ok:
                logger.critical(f"Login falhou para o worker '{nome_fluxo}'. A thread será encerrada.")
                return 
            
            logger.success(f"Login realizado com sucesso para '{nome_fluxo}'. Executando loop do worker.")
            
            funcao_fluxo(page, config) 
            
            logger.info(f"Worker '{nome_fluxo}' encerrou seu loop (isso não deveria acontecer).")

        except Exception as e:
            mensagem_erro = f"Ocorreu um erro fatal e não tratado no worker '{nome_fluxo}': {e}"
            logger.critical(mensagem_erro)
        
        finally:
            # Garante que tudo criado na thread seja fechado nela
            if context:
                context.close()
            if browser:
                browser.close()
            logger.error(f"Thread do worker '{nome_fluxo}' foi finalizada.")

# ===================================================================
# MAIN (Orquestrador de Threads - CORRIGIDO)
# ===================================================================
def main():
    config = carregar_config()
    if not config:
        logger.critical("Não foi possível carregar o config.json. Encerrando.")
        return
    
    logger.info("Iniciando Orquestrador de Workers RPA...")
    logger.warning("Lembre-se de iniciar o 'poller.py' e o 'writer.py' em terminais separados.")

    # --- CORREÇÃO: O 'with' foi REMOVIDO daqui ---
    threads = [] 
    
    try:
        # --- Lançamento dos Workers em Threads ---
        
        # --- Worker 1: Conferência ---
        logger.info("Preparando worker 'conferencia'...")
        t1 = threading.Thread(
            target=executar_fluxo, 
            # --- CORREÇÃO: 'browser' removido dos args ---
            args=("conferencia", fluxo_conferencia_worker, config),
            daemon=True 
        )
        threads.append(t1)

        # --- Worker 2: Verificar Emissão ---
        logger.info("Preparando worker 'verificar_emissao'...")
        t2 = threading.Thread(
            target=executar_fluxo, 
            args=("verificar_emissao", fluxo_verificar_emissao_worker, config),
            daemon=True
        )
        threads.append(t2)
        
        # --- Inicia as threads ---
        for t in threads:
            t.start()
            logger.success(f"Thread {t.name} ({'Conferência' if t is t1 else 'Verificar Emissão'}) iniciada.")
        
        # --- Loop de monitoramento ---
        logger.info("Workers em execução. Pressione Ctrl+C para parar.")
        while True:
            alguma_thread_viva = False
            for t in threads:
                if t.is_alive():
                    alguma_thread_viva = True
                    break
            
            if not alguma_thread_viva:
                logger.critical("Todas as threads dos workers morreram! Encerrando...")
                break
                
            time.sleep(10)

    except KeyboardInterrupt:
        logger.warning("Execução interrompida pelo usuário (Ctrl+C). Encerrando...")
    
    except Exception as e:
        mensagem_erro = f"Erro fatal no Orquestrador (main): {e}"
        logger.critical(mensagem_erro)
    
    finally:
        logger.info("Automação finalizada.")

if __name__ == "__main__":
    main()