from collections.abc import AsyncGenerator

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


# 1. Definição das variáveis de ambiente com Pydantic
class Settings(BaseSettings):
    DATABASE_URL: str

    # Configuração para ler automaticamente do arquivo .env
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Instancia as configurações (ele vai ler o .env neste momento)
settings = Settings()

# 2. Configuração do Banco de Dados
esus_engine = create_async_engine(settings.DATABASE_URL, echo=False)

# Uso do async_sessionmaker (Padrão correto para SQLAlchemy 2.0+)
EsusSessionLocal = async_sessionmaker(bind=esus_engine, expire_on_commit=False)


async def get_esus_session() -> AsyncGenerator[AsyncSession, None]:
    """Injeta a sessão do banco de dados nas rotas."""
    async with EsusSessionLocal() as session:
        yield session
