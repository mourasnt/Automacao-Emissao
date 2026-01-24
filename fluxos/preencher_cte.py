import re
from playwright.sync_api import Page, Locator, TimeoutError
from loguru import logger
from typing import Dict, Any
from utils.fluxo_utils import extrair_dados_dos_cards_cte 


def preencher_cte(page: Page, card: Locator, numero_lt: str) -> Dict[str, Any]:
    try:
        # 1. ENCONTRAR O BOTÃO DE AUTORIZADO
        cte_label = card.locator("div", has_text=re.compile(r"^\s*CT-e\s*$"))
        if cte_label.count() == 0:
            motivo = f"A etiqueta 'CT-e' não foi encontrada no card."
            logger.error(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
            return {"status": "falha_rpa", "motivo": motivo}

        cte_row_container = cte_label.first.locator("xpath=..")
        botao_autorizado = cte_row_container.locator('button:has(span[style*="margin-top"])').first

        if botao_autorizado.count() == 0:
            motivo = "Botão 'Autorizado' não encontrado na linha do CT-e."
            logger.error(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
            return {"status": "falha_rpa", "motivo": motivo}
            
        # 2. CLICAR E NAVEGAR
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            botao_autorizado.click()

        # 3. EXTRAIR OS DADOS DA NOVA PÁGINA
        dados_ctes = extrair_dados_dos_cards_cte(page, numero_lt)
        
        if not dados_ctes:
            motivo = "Nenhum dado de CT-e foi extraído após o clique."
            logger.warning(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
            return {"status": "sem_dados", "motivo": motivo}
        
        # 4. PROCESSAR DADOS E RETORNAR
        numeros_ctes_lista = [cte["numero"] for cte in dados_ctes]
        numeros_ctes_str = "/".join(numeros_ctes_lista)
        valor_total_float = sum(cte["valor"] for cte in dados_ctes)
        # Formata para o padrão brasileiro (ex: 1500,50)
        valor_total_str = f"{valor_total_float:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") 

        return {
            "status": "sucesso",
            "numeros_ctes": numeros_ctes_str,
            "valor_total": valor_total_str
        }

    except TimeoutError as e:
        detalhe_erro = str(e).split('\n')[0]
        motivo = f"Timeout no fluxo de preenchimento: {detalhe_erro}"
        logger.error(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
        return {"status": "falha_rpa", "motivo": motivo}
    
    except Exception as e:
        motivo = f"Erro inesperado no fluxo de preenchimento: {e}"
        logger.critical(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
        return {"status": "falha_rpa", "motivo": motivo}