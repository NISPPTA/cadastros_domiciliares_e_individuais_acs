from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Importação exclusiva do nosso módulo de auditoria
from src.modules.auditoria.router import router as auditoria_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciador de Contexto de Ciclo de Vida."""
    print("🚀 Painel de Auditoria iniciado com sucesso!")
    yield
    print("🛑 Encerrando a aplicação com segurança...")


# Instância principal do FastAPI
app = FastAPI(
    title="Auditoria Cadastral - e-SUS PEC",
    description="Painel web para auditoria de integridade cadastral no e-SUS PEC.",
    version="1.0.0",
    contact={
        "name": "Secretaria Municipal de Saúde - Paraguaçu Paulista",
    },
    lifespan=lifespan,
)

# Configuração de Segurança (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registo do Roteador de Auditoria
app.include_router(auditoria_router)


@app.get("/", include_in_schema=False)
async def root():
    """Redireciona a raiz diretamente para a interface gráfica."""
    return RedirectResponse(url="/auditoria/")
