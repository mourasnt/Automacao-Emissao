import re
from playwright.sync_api import Page, Locator, TimeoutError
from loguru import logger
from typing import Dict, Any
from utils.fluxo_utils import extrair_dados_dos_cards_mdfe


def preencher_mdfe(page: Page, card: Locator, numero_lt: str) -> Dict[str, Any]:
    try:
        # 1. Localiza o rótulo "MDF-e" (seu seletor original)
        mdfe_label = card.locator("div").filter(has_text=re.compile(r"^MDF-eAutorizado$")).get_by_role("button")
        if mdfe_label.count() == 0:
            motivo = "Nenhuma seção MDF-e encontrada no card."
            return {"status": "nao_aplicavel", "motivo": motivo} # <--- MUDANÇA

        # 2. Encontra o container da "linha" (seu seletor original)
        mdfe_row_container = mdfe_label.first.locator("xpath=../..")

        # 3. Dentro do container, localiza o botão de status.
        botao_status_mdfe = mdfe_row_container.locator("button")
        if botao_status_mdfe.count() == 0:
            motivo = "Botão de status não encontrado na linha do MDF-e."
            logger.error(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
            return {"status": "falha_rpa", "motivo": motivo} # <--- MUDANÇA

        # 4. Verificação de status (só clica se for 'Autorizado')
        status_texto = botao_status_mdfe.first.inner_text().strip()
        if "autorizado" not in status_texto.lower():
            motivo = f"MDF-e não está 'Autorizado' (Status: {status_texto})."
            return {"status": "nao_aplicavel", "motivo": motivo} # <--- MUDANÇA

        # 5. CAMINHO FELIZ: Clicar e extrair
        with page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            botao_status_mdfe.click()
        
        # 6. Extrair dados da nova página
        dados_mdfes = extrair_dados_dos_cards_mdfe(page)
        if not dados_mdfes:
            motivo = "Nenhum dado de MDF-e foi extraído após o clique."
            logger.warning(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
            return {"status": "sem_dados", "motivo": motivo} # <--- MUDANÇA
        
        # 7. Processar dados e retornar
        numeros_mdfes = "/".join([mdfe["numero"] for mdfe in dados_mdfes])
        chaves = "/".join([mdfe["chave"] for mdfe in dados_mdfes])

        return {
            "status": "sucesso",
            "numeros_mdfes": numeros_mdfes,
            "chaves": chaves
        }

    except TimeoutError as e:
        detalhe_erro = str(e).split('\n')[0]
        motivo = f"Timeout ao clicar/extrair MDF-e: {detalhe_erro}"
        logger.error(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
        return {"status": "falha_rpa", "motivo": motivo}
    
    except Exception as e:
        motivo = f"Erro inesperado ao processar MDF-e: {e}"
        logger.critical(f"[Worker Emissão] [LT {numero_lt}] {motivo}")
        return {"status": "falha_rpa", "motivo": motivo}