from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import HTMLResponse
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

    return templates.TemplateResponse(
        "auditoria.html",
        {
            "request": request,
            "agentes": agentes,
            "agente_selecionado": agente_id,
            "relatorio": relatorio,
        },
    )


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
