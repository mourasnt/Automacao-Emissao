from playwright.sync_api import Page, TimeoutError
from loguru import logger

def fluxo_login(page: Page, usuario: str, senha: str, max_tentativas: int = 3, output_path: str = "dados/auth.json") -> bool:

    # 1. Checa se já está logado antes de qualquer tentativa
    if "#/login" not in page.url.lower():
        logger.info("Sessão já ativa (URL não é de login). Pulando login.")
        return True

    # 2. Loop único de tentativas de login
    for tentativa in range(1, max_tentativas + 1):
        # REMOVIDO: print("-" * 40)
        logger.info(f"Tentativa de login {tentativa}/{max_tentativas}...")
        try:
            # Garante que a página é a de login antes de preencher
            if "#/login" not in page.url.lower():
                  logger.info("A página não é mais a de login. Login provavelmente bem-sucedido em outra etapa.")
                  return True

            # Preenche os campos
            page.get_by_role("textbox", name="CPF ou E-mail").fill(usuario)
            page.get_by_role("button", name="Continuar").click()
            page.get_by_placeholder("******").fill(senha)
            
            with page.expect_navigation(timeout=15000): # Espera por até 15 segundos
                page.get_by_role("button", name="Entrar").click()

            # Se o código chegou aqui, a navegação ocorreu com sucesso.
            page.context.storage_state(path=output_path)
            return True

        except TimeoutError:
            logger.warning(f"Tentativa {tentativa} falhou: a página não redirecionou a tempo.")
            # Verifica se há uma mensagem de erro visível
            erro_locator = page.locator("text=/usuário ou senha inválidos/i") # Ajuste o texto se necessário
            if erro_locator.is_visible():
                logger.error("Mensagem de 'usuário ou senha inválidos' detectada. Abortando.")
                return False
            
            # Se não for erro de senha, pode ser lentidão. Recarrega para a próxima tentativa.
            if tentativa < max_tentativas:
                logger.debug("Recarregando a página para a próxima tentativa...")
                page.reload()
                page.wait_for_load_state('domcontentloaded')

        except Exception as e:
            logger.error(f"Erro inesperado na tentativa {tentativa}: {e}")
            if tentativa < max_tentativas:
                 page.reload()

    logger.critical(f"Login falhou após {max_tentativas} tentativas.")
    return False