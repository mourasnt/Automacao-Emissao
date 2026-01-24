from dataclasses import dataclass
from utils.helpers import validar_e_limpar_placa, carregar_config

def _limpar_e_converter_valor(valor_str: str) -> float | None:
    """
    Tenta limpar e converter uma string para float.
    Retorna o float se conseguir, ou None se falhar.
    """
    try:
        if not isinstance(valor_str, str):
            valor_str = str(valor_str)

        valor_limpo = valor_str.replace("R$", "").strip().replace(".", "").replace(",", ".")
        
        if not valor_limpo: # Se a string ficar vazia
            return None

        return float(valor_limpo)
    except (ValueError, TypeError):
        # Se a conversão falhar (ex: a string era "conferir"), retorna None
        return None

@dataclass
class Carga:
    id_alvo: str
    numero_lt: str
    frete: float
    pedagio: float
    origem: str
    destino: str
    motorista: str
    placa: str
    placa2: str
    perfil: str
    status: str
    status_emissao: str

    @classmethod
    def from_row(cls, row):
        """
        Cria um objeto Carga a partir de uma linha, com validação e ações configuráveis
        para valores inválidos (usar padrão ou pular linha).
        """
        try:
            config = carregar_config()
            # Pega a ação do config, com 'usar_padrao' como fallback seguro
            acao_valor_invalido = config.get('acao_valor_invalido', 'pular_linha').lower()

            # --- Lógica para Frete ---
            frete_original = row["Tabela Frete"]
            frete = _limpar_e_converter_valor(frete_original)

            if frete is None: # Se a conversão falhou
                if acao_valor_invalido == 'pular_linha':
                    return None # PULA A LINHA
                else: # Ação padrão é 'usar_padrao'
                    frete = config.get('default_frete')

            # --- Lógica para Pedágio ---
            pedagio_original = row["Pedágio"]
            pedagio = _limpar_e_converter_valor(pedagio_original)

            if pedagio is None: # Se a conversão falhou
                if acao_valor_invalido == 'pular_linha':
                    print(f"[INFO] N° Carga '{row['N° Carga']}': Valor de pedágio '{pedagio_original}' inválido. Pulando linha conforme configuração.")
                    return None # PULA A LINHA
                else: # Ação padrão é 'usar_padrao'
                    pedagio = config.get('default_pedagio', 0.0)
                    print(f"[INFO] N° Carga '{row['N° Carga']}': Valor de pedágio '{pedagio_original}' inválido. Usando padrão: {pedagio}")
            
            # Validação das placas (continua igual)
            placa = validar_e_limpar_placa(row["Placa"])
            placa2 = validar_e_limpar_placa(row["Placa 2"])
            
            return cls(
                id_alvo=row["ID 3ZX"],
                numero_lt=row["N° Carga"],
                frete=frete,
                pedagio=pedagio,
                origem=row["Origem"],
                destino=row["Destino"],
                motorista=row["Motorista"],
                placa=placa,
                placa2=placa2,
                perfil="CARRETA" if placa2 else "TRUCK",
                status=row["Status"],
                status_emissao=row["Status de emissão"]
            )
        except KeyError as e:
            print(f"[ERROR] Coluna não encontrada na linha com N° Carga '{row.get('N° Carga', 'N/A')}': {e}. Pulando linha.")
            return None
        except Exception as e:
            print(f"[ERROR] Erro inesperado ao processar linha com N° Carga '{row.get('N° Carga', 'N/A')}': {e}. Pulando linha.")
            return None