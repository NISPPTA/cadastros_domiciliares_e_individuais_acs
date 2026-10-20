import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Importação exclusiva do nosso módulo de auditoria
from src.modules.auditoria.router import router as auditoria_router

# Instancia o logger padrão integrado ao ambiente ASGI (Uvicorn)
logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Gerenciador de Contexto de Ciclo de Vida da Aplicação."""
    logger.info("🚀 Painel de Auditoria iniciado com sucesso!")
    yield
    logger.info("🛑 Encerrando a aplicação com segurança...")


def create_app() -> FastAPI:
    """
    Application Factory: Padrão Sênior para inicialização limpa.
    Evita estado global solto e facilita a injeção de dependências em testes.
    """
    _app = FastAPI(
        title="Auditoria Cadastral - e-SUS PEC",
        description="Painel web para auditoria de integridade cadastral no e-SUS PEC.",
        version="1.0.0",
        contact={
            "name": "Secretaria Municipal de Saúde - Paraguaçu Paulista",
        },
        lifespan=lifespan,
    )

    # Configuração de Segurança (CORS)
    # Nota de Segurança: Em produção estrita, substitua ["*"] pelo domínio real do frontend
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registro do Roteador de Auditoria
    _app.include_router(auditoria_router)

    @_app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        """Redireciona a raiz diretamente para a interface gráfica."""
        # O status 307 garante que o redirecionamento mantenha o método HTTP
        return RedirectResponse(
            url="/auditoria/", status_code=status.HTTP_307_TEMPORARY_REDIRECT
        )

    return _app


# Instância principal que o Uvicorn irá consumir
app = create_app()
