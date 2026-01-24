import json

def validar_e_limpar_placa(valor_placa):
    if not isinstance(valor_placa, str):
        return None

    placa_limpa = valor_placa.strip().replace('-', '').upper()

    if len(placa_limpa) == 7 and placa_limpa.isalnum():
        return placa_limpa
    
    return None

def carregar_config(config_path='utils/config.json'):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None