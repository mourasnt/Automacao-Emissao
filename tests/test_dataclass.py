import pytest
from dados.dataclass import _limpar_e_converter_valor, Carga


def test_limpar_convert_valid():
    assert _limpar_e_converter_valor("R$ 1.234,56") == 1234.56


def test_limpar_convert_invalid():
    assert _limpar_e_converter_valor("conferir") is None


def test_carga_from_row_valid(monkeypatch):
    # For this test we patch carregar_config to return sensible defaults
    monkeypatch.setattr("dados.dataclass.carregar_config", lambda: {"acao_valor_invalido":"usar_padrao","default_pedagio":0.0,"default_frete":100.0})
    row = {
        "Tabela Frete":"R$ 100,00",
        "Pedágio":"R$ 10,00",
        "Placa":"ABC-1234",
        "Placa 2":"",
        "ID 3ZX":"ID1",
        "N° Carga":"LT1",
        "Origem":"A",
        "Destino":"B",
        "Motorista":"X",
        "Status":"OK",
        "Status de emissão":"Pendente"
    }
    c = Carga.from_row(row)
    assert c is not None
    assert c.frete == 100.0
    assert c.pedagio == 10.0
    assert c.numero_lt == "LT1"
