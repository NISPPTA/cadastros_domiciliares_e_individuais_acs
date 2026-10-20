from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_esus_session
from src.modules.auditoria.pdf_service import AuditoriaPDFService
from src.modules.auditoria.service import AuditoriaCadastralService

router = APIRouter(prefix="/auditoria", tags=["Auditoria Cadastral e-SUS"])
templates = Jinja2Templates(directory="templates")
service = AuditoriaCadastralService()

# Usando Annotated: O Ruff não reclama e o código fica mais limpo e moderno
DbSession = Annotated[AsyncSession, Depends(get_esus_session)]


@router.get("/", response_class=HTMLResponse)
async def carregar_painel_auditoria(
    request: Request,
    esus_session: DbSession,
    agente_id: int | None = None,
):
    agentes = await service.listar_acs_ativos(esus_session)
    relatorio = None

    if agente_id:
        relatorio = await service.auditar_acs(esus_session, agente_id)

    context = {
        "request": request,
        "agentes": agentes,
        "agente_selecionado": agente_id,
        "relatorio": relatorio,
    }

    return templates.TemplateResponse(request, "auditoria.html", context)


@router.get("/pdf/{agente_id}", summary="Baixar Laudo em PDF")
async def baixar_laudo_pdf(agente_id: int, esus_session: DbSession):
    """Gera e faz o download do laudo de auditoria em PDF."""
    relatorio = await service.auditar_acs(esus_session, agente_id)

    if not relatorio or relatorio.total_cadastros_individuais == 0:
        raise HTTPException(status_code=404, detail="Sem dados para este agente.")

    pdf_service = AuditoriaPDFService()
    pdf_bytes = pdf_service.gerar_laudo_pdf(relatorio)

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=laudo_acs_{agente_id}.pdf"
        },
    )


@router.get("/api/domicilios/{agente_id}", summary="API - Domicílios Auditados")
async def api_domicilios(
    agente_id: int, esus_session: DbSession, limit: int = 10, offset: int = 0
):
    """Retorna os cadastros domiciliares com paginação dinâmica."""
    return await service.listar_domicilios_detalhado(
        esus_session, agente_id, limit, offset
    )


@router.get(
    "/api/individuos/{agente_id}", summary="API - Indivíduos e Doenças Crônicas"
)
async def api_individuos(
    agente_id: int, esus_session: DbSession, limit: int = 10, offset: int = 0
):
    """Retorna a folha clínica e telefones dos munícipes com contagem de repetição de CPF."""
    return await service.listar_individuos_detalhado(
        esus_session, agente_id, limit, offset
    )


@router.get(
    "/api/duplicidades/{agente_id}", summary="API - Cidadãos Cadastrados em Duplicidade"
)
async def api_duplicidades(
    agente_id: int, esus_session: DbSession, limit: int = 10, offset: int = 0
):
    """Identifica munícipes cadastrados mais de uma vez pelo mesmo profissional (inflação de meta)."""
    return await service.listar_duplicidades_agente(
        esus_session, agente_id, limit, offset
    )


# 1. Endpoint do Autocomplete (busca dinâmica a partir de 3 caracteres)
@router.get("/api/busca-agentes", summary="Busca Dinâmica de Agentes")
async def buscar_agentes_dinamico(
    q: str = Query(
        ..., min_length=1, description="Termo de busca com ao menos 3 caracteres"
    ),
    esus_session: DbSession = None,
):
    if len(q.strip()) < 3:
        return JSONResponse(content=[])
    agentes = await service.buscar_acs_por_termo(esus_session, q.strip())
    return JSONResponse(content=agentes)


@router.get("/api/busca-endereco", summary="API - Busca Reversa Territorial")
async def api_busca_endereco(
    rua: str = Query(..., min_length=3),
    numero: str | None = Query(None),
    esus_session: DbSession = None,
):
    """Retorna o ACS responsável por um endereço específico."""
    return await service.buscar_reversa_endereco(esus_session, rua, numero)


@router.get("/api/busca-logradouro", summary="Autocomplete de Ruas")
async def autocomplete_logradouro(
    q: str = Query(..., min_length=3, description="Mínimo 3 letras da rua"),
    esus_session: DbSession = None,
):
    """API para o autocomplete do campo de endereço na Busca Reversa."""
    if len(q.strip()) < 3:
        return JSONResponse(content=[])
    ruas = await service.buscar_logradouros_autocomplete(esus_session, q.strip())
    return JSONResponse(content=ruas)


@router.get(
    "/api/ficha-domiciliar/{id_ficha}",
    summary="API - Detalhes do Prontuário Domiciliar",
)
async def api_ficha_domiciliar(id_ficha: int, esus_session: DbSession = None):
    """Retorna os dados detalhados (saneamento, moradia, animais) de uma ficha domiciliar."""
    ficha = await service.buscar_detalhes_ficha_domiciliar(esus_session, id_ficha)
    if not ficha:
        raise HTTPException(
            status_code=404, detail="Ficha não encontrada no banco de dados."
        )
    return JSONResponse(content=ficha)


@router.get(
    "/api/ficha-domiciliar/{id_ficha}/visitas",
    summary="API - Histórico de Visitas Paginado",
)
async def api_visitas_domiciliar(
    id_ficha: int, limit: int = 5, offset: int = 0, esus_session: DbSession = None
):
    """Retorna o histórico de visitas paginado de um domicílio específico."""
    dados = await service.buscar_visitas_domicilio_paginado(
        esus_session, id_ficha, limit, offset
    )
    return JSONResponse(content=dados)


# 2. Rota que renderiza a nova página de Inspeção Pericial
@router.get("/inspecao/", summary="Página de Inspeção Pericial (Sindicância)")
async def carregar_tela_inspecao(
    request: Request,
    agente_id: int | None = Query(None),
    esus_session: DbSession = None,
):
    agente_selecionado = None
    relatorio = None

    if agente_id:
        # Busca apenas os indicadores do laudo principal
        relatorio = await service.auditar_acs(esus_session, agente_id)
        agente_selecionado = {
            "id": agente_id,
            "nome": relatorio.nome_acs,
        }
        # As tabelas agora são carregadas exclusivamente via AJAX para acelerar o carregamento.

    context = {
        "request": request,
        "agente_selecionado": agente_selecionado,
        "relatorio": relatorio,
    }
    return templates.TemplateResponse(request, "inspecao.html", context)


@router.get("/informacoes/{id_ficha}", response_class=HTMLResponse)
async def pagina_informacoes_cidadao(
    request: Request, id_ficha: int, esus_session: DbSession = None
):
    """Renderiza em nova guia as Informações do Cidadão."""
    dados = await service.buscar_informacoes_cidadao(esus_session, id_ficha)
    if not dados:
        raise HTTPException(status_code=404, detail="Ficha Individual não encontrada.")

    context = {"request": request, "cidadao": dados}
    return templates.TemplateResponse(request, "informacoes_cidadao.html", context)


@router.get(
    "/api/informacoes/{id_ficha}/agendamentos",
    summary="API - Histórico de Atendimentos do Cidadão",
)
async def api_agendamentos_cidadao(
    id_ficha: int, limit: int = 5, offset: int = 0, esus_session: DbSession = None
):
    """Retorna o histórico de atendimentos reais paginado de um munícipe."""
    dados = await service.buscar_agendamentos_cidadao_paginado(
        esus_session, id_ficha, limit, offset
    )
    return JSONResponse(content=dados)
