from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# URL do banco do e-SUS PEC (Ajuste usuário e senha)
ESUS_DATABASE_URL = "postgresql+asyncpg://postgres:sua_senha@localhost:5432/esus"

esus_engine = create_async_engine(ESUS_DATABASE_URL, echo=False)
EsusSessionLocal = sessionmaker(esus_engine, class_=AsyncSession, expire_on_commit=False)

async def get_esus_session() -> AsyncGenerator[AsyncSession, None]:
    async with EsusSessionLocal() as session:
        yield session