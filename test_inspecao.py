"""Validação de Integridade e Contratos da Bancada Pericial."""

from bs4 import BeautifulSoup


def test_estrutura_html_seguranca():
    with open("templates/inspecao.html", "r", encoding="utf-8") as f:
        html = f.read()

    # 1. Não deve haver inserções inseguras no JavaScript
    assert "insertAdjacentHTML" not in html
    assert "innerHTML =" not in html
    assert "eval(" not in html

    # 2. Presença dos nós de acessibilidade WCAG
    soup = BeautifulSoup(html, "html.parser")

    # Diálogo do modal
    modal = soup.find("div", {"id": "modal_ficha"})
    assert modal is not None
    assert modal.get("role") == "dialog"
    assert modal.get("aria-modal") == "true"
    assert modal.get("aria-labelledby") == "modal_ficha_titulo"

    # Tablist e abas
    tablist = soup.find("div", {"role": "tablist"})
    assert tablist is not None
    tabs = tablist.find_all("button", {"role": "tab"})
    assert len(tabs) == 4

    # Identificadores de paginação e tabelas intactos
    for tipo in ["dup", "dom", "ind"]:
        assert soup.find("tbody", {"id": f"tbody_{tipo}"}) is not None
        assert soup.find("select", {"id": f"select_limit_{tipo}"}) is not None
        assert soup.find("button", {"id": f"btn_prev_{tipo}"}) is not None
        assert soup.find("button", {"id": f"btn_next_{tipo}"}) is not None
        assert soup.find("span", {"id": f"info_pag_{tipo}"}) is not None

    # Autocomplete
    input_rua = soup.find("input", {"id": "input_rua"})
    assert input_rua.get("role") == "combobox"
    assert input_rua.get("aria-autocomplete") == "list"
    assert soup.find("ul", {"id": "lista_ruas"}) is not None

    # Modal controles de visita
    assert soup.find("tbody", {"id": "m_visitas_tbody"}) is not None
    assert soup.find("span", {"id": "m_visitas_info"}) is not None
    assert soup.find("button", {"id": "btn_m_prev"}) is not None
    assert soup.find("button", {"id": "btn_m_next"}) is not None


def test_contrato_urls():
    with open("templates/inspecao.html", "r", encoding="utf-8") as f:
        js = f.read()

    # Preservação das rotas oficiais de backend
    assert "/auditoria/api/duplicidades/" in js
    assert "/auditoria/api/domicilios/" in js
    assert "/auditoria/api/individuos/" in js
    assert "/auditoria/api/busca-endereco" in js
    assert "/auditoria/api/busca-logradouro" in js
    assert "/auditoria/api/ficha-domiciliar/" in js
    assert "/auditoria/informacoes/" in js
