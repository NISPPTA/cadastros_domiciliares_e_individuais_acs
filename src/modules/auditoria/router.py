from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.database import get_esus_session
from src.modules.auditoria.service import AuditoriaCadastralService

router = APIRouter(prefix="/auditoria", tags=["Auditoria Cadastral e-SUS"])
templates = Jinja2Templates(directory="templates")
service = AuditoriaCadastralService()


@router.get("/", response_class=HTMLResponse)
async def carregar_painel_auditoria(
    request: Request,
    agente_id: int | None = None,
    esus_session: AsyncSession = Depends(get_esus_session),
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