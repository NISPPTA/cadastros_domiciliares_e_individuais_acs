from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

# Importação dos nossos módulos especialistas
from src.modules.avaliacoes.router import router as avaliacoes_router
from src.modules.auditoria.router import router as auditoria_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerenciador de Contexto de Ciclo de Vida (Substitui os antigos @app.on_event).
    Tudo antes do 'yield' roda no startup. Tudo depois roda no shutdown.
    """
    # Exemplo: Aqui você pode testar a conexão com o banco ou carregar ML models
    print("🚀 API IFA e Auditoria iniciada com sucesso!")
    
    yield  # A aplicação roda neste ponto
    
    # Exemplo: Aqui ocorre o graceful shutdown (fechamento seguro de conexões)
    print("🛑 Encerrando a aplicação com segurança...")

# Instância principal do FastAPI
app = FastAPI(
    title="Sistema Integrado de Avaliação (IFA) e Auditoria",
    description="Motor de cálculo de desempenho para ACS/ACE e auditoria de integridade cadastral no e-SUS PEC.",
    version="0.2.0",
    contact={
        "name": "Secretaria Municipal de Saúde - Paraguaçu Paulista",
    },
    lifespan=lifespan,
)

# Configuração de Segurança (CORS) - Permite requisições de front-ends externos
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja para os domínios do município
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registro dos Roteadores (Plugging the modules)
# O módulo de avaliações ficará sob o prefixo de versionamento da API
app.include_router(avaliacoes_router, prefix="/api/v1")

# O módulo de auditoria não precisa de prefixo aqui, pois já o definimos como "/auditoria" no seu próprio router
app.include_router(auditoria_router)

@app.get("/", include_in_schema=False)
async def root():
    """
    Endpoint raiz. Redireciona usuários desavisados diretamente para a 
    interface gráfica (Painel Web) em vez de mostrar um JSON vazio.
    """
    return RedirectResponse(url="/auditoria/")