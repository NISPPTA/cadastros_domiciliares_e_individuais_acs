from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(slots=True, kw_only=True)
class RelatorioAuditoriaACS:
    profissional_id: int
    nome_acs: str
    total_cadastros_individuais: int
    total_domicilios: int
    taxa_eficiencia: float
    classificacao: str
    detalhes_comodos: list[dict[str, Any]]
    telefones_duplicados: list[dict[str, Any]]
    dados_moradores: list[dict[str, Any]]
    dados_saude: dict[str, Any]
    pontos_atencao: list[str]


class AuditoriaCadastralService:
    # --- Parâmetros e Limites de Auditoria (Magic Numbers extraídos) ---
    LIMITE_COMODOS_PERCENTUAL = 70.0
    PENALIDADE_COMODOS = 25.0

    LIMITE_TELEFONES_CRITICO = 50
    LIMITE_TELEFONES_ATENCAO = 10
    PENALIDADE_TELEFONES_CRITICO = 25.0
    PENALIDADE_TELEFONES_ATENCAO = 15.0

    LIMITE_MORADORES_UNIPESSOAL = 50.0
    PENALIDADE_MORADORES = 20.0

    LIMITE_HIPERTENSAO_MINIMO = 10.0
    PENALIDADE_HIPERTENSAO = 15.0
    PENALIDADE_RESPIRATORIA = 10.0

    async def listar_acs_ativos(
        self, esus_session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Recupera todos os profissionais cadastrados como ACS no e-SUS PEC."""
        query = text("""
            SELECT DISTINCT 
                dp.co_seq_dim_profissional AS id,
                dp.no_profissional AS nome,
                dp.nu_cns AS cns
            FROM tb_dim_profissional dp
            JOIN tb_dim_cbo cbo ON cbo.co_seq_dim_cbo = dp.co_dim_cbo
            WHERE cbo.nu_cbo ILIKE '515105%'
               OR cbo.ds_cbo ILIKE '%AGENTE COMUNITARIO%'
            ORDER BY dp.no_profissional ASC;
        """)
        result = await esus_session.execute(query)
        return [
            {"id": row.id, "nome": row.nome, "cns": row.cns} for row in result.all()
        ]

    async def auditar_acs(
        self, esus_session: AsyncSession, profissional_id: int
    ) -> RelatorioAuditoriaACS:
        """Executa a auditoria completa de um agente delegando responsabilidades a métodos especialistas."""
        params = {"id": profissional_id}

        # Extração de dados (Executados sequencialmente para respeitar o event loop do AsyncSession)
        nome_acs = await self._buscar_nome_acs(esus_session, params)
        comodos_list = await self._buscar_comodos(esus_session, params)
        telefones_list = await self._buscar_telefones_duplicados(esus_session, params)
        moradores_list = await self._buscar_moradores(esus_session, params)
        saude_dict = await self._buscar_dados_saude(esus_session, params)

        total_domicilios = sum(item["total"] for item in comodos_list)
        total_ind = saude_dict["total_cadastros"]

        # Processamento das regras de negócio e cálculo de pontuação
        taxa_eficiencia, pontos_atencao = self._calcular_eficiencia_e_alertas(
            comodos_list, telefones_list, moradores_list, saude_dict, total_ind
        )
        classificacao = self._determinar_classificacao(taxa_eficiencia)

        return RelatorioAuditoriaACS(
            profissional_id=profissional_id,
            nome_acs=nome_acs,
            total_cadastros_individuais=total_ind,
            total_domicilios=total_domicilios,
            taxa_eficiencia=taxa_eficiencia,
            classificacao=classificacao,
            detalhes_comodos=comodos_list,
            telefones_duplicados=telefones_list,
            dados_moradores=moradores_list,
            dados_saude=saude_dict,
            pontos_atencao=pontos_atencao,
        )

    # ==========================================
    # MÉTODOS PRIVADOS DE EXTRAÇÃO DE DADOS (DB)
    # ==========================================

    async def _buscar_nome_acs(
        self, session: AsyncSession, params: dict[str, Any]
    ) -> str:
        query = text(
            "SELECT no_profissional FROM tb_dim_profissional WHERE co_seq_dim_profissional = :id"
        )
        return (await session.execute(query, params)).scalar() or "Não Identificado"

    async def _buscar_comodos(
        self, session: AsyncSession, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT 
                COALESCE(fd.nu_comodo, 0) AS qtd_comodos,
                COUNT(fd.co_seq_fat_cad_domiciliar) AS total,
                ROUND(COUNT(fd.co_seq_fat_cad_domiciliar) * 100.0 / NULLIF(SUM(COUNT(fd.co_seq_fat_cad_domiciliar)) OVER(), 0), 2) AS percentual
            FROM tb_fat_cad_domiciliar fd
            WHERE fd.co_dim_profissional = :id
            GROUP BY fd.nu_comodo
            ORDER BY total DESC;
        """)
        result = await session.execute(query, params)
        return [
            {
                "comodos": r.qtd_comodos,
                "total": r.total,
                "percentual": float(r.percentual or 0),
            }
            for r in result.all()
        ]

    async def _buscar_telefones_duplicados(
        self, session: AsyncSession, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT 
                COALESCE(c.nu_telefone_celular, c.nu_telefone_contato) AS telefone,
                COUNT(c.co_seq_cidadao) AS qtd
            FROM tb_fat_cad_individual fi
            JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = fi.co_fat_cidadao_pec
            JOIN tb_cidadao c ON c.co_seq_cidadao = fcp.co_cidadao
            WHERE fi.co_dim_profissional = :id
              AND (c.nu_telefone_celular IS NOT NULL OR c.nu_telefone_contato IS NOT NULL)
            GROUP BY COALESCE(c.nu_telefone_celular, c.nu_telefone_contato)
            HAVING COUNT(c.co_seq_cidadao) > 3
            ORDER BY qtd DESC
            LIMIT 10;
        """)
        result = await session.execute(query, params)
        return [{"telefone": r.telefone, "qtd": r.qtd} for r in result.all()]

    async def _buscar_moradores(
        self, session: AsyncSession, params: dict[str, Any]
    ) -> list[dict[str, Any]]:
        query = text("""
            SELECT 
                fd.qt_morador AS qtd_morador,
                COUNT(fd.co_seq_fat_cad_domiciliar) AS total,
                ROUND(COUNT(fd.co_seq_fat_cad_domiciliar) * 100.0 / NULLIF(SUM(COUNT(fd.co_seq_fat_cad_domiciliar)) OVER(), 0), 2) AS percentual
            FROM tb_fat_cad_domiciliar fd
            WHERE fd.co_dim_profissional = :id
            GROUP BY fd.qt_morador
            ORDER BY total DESC;
        """)
        result = await session.execute(query, params)
        return [
            {
                "qtd_morador": r.qtd_morador,
                "total": r.total,
                "percentual": float(r.percentual or 0),
            }
            for r in result.all()
        ]

    async def _buscar_dados_saude(
        self, session: AsyncSession, params: dict[str, Any]
    ) -> dict[str, Any]:
        query = text("""
            SELECT 
                COUNT(fi.co_seq_fat_cad_individual) AS total_cadastros,
                COUNT(CASE WHEN fi.st_hipertensao_arterial::text IN ('1', 'true') THEN 1 END) AS hipertensos,
                COUNT(CASE WHEN fi.st_diabete::text IN ('1', 'true') THEN 1 END) AS diabeticos,
                COUNT(CASE WHEN fi.st_doenca_cardiaca::text IN ('1', 'true') THEN 1 END) AS cardiopatas,
                COUNT(CASE WHEN fi.st_doenca_respiratoria::text IN ('1', 'true') THEN 1 END) AS respiratoria,
                COUNT(CASE WHEN fi.st_cancer::text IN ('1', 'true') THEN 1 END) AS cancer,
                COUNT(CASE WHEN fi.st_fumante::text IN ('1', 'true') THEN 1 END) AS fumantes
            FROM tb_fat_cad_individual fi
            WHERE fi.co_dim_profissional = :id;
        """)
        r_saude = (await session.execute(query, params)).first()

        if not r_saude:
            return {
                "total_cadastros": 0,
                "hipertensos": 0,
                "diabeticos": 0,
                "cardiopatas": 0,
                "respiratoria": 0,
                "cancer": 0,
                "fumantes": 0,
            }

        return {
            "total_cadastros": r_saude.total_cadastros or 0,
            "hipertensos": r_saude.hipertensos or 0,
            "diabeticos": r_saude.diabeticos or 0,
            "cardiopatas": r_saude.cardiopatas or 0,
            "respiratoria": r_saude.respiratoria or 0,
            "cancer": r_saude.cancer or 0,
            "fumantes": r_saude.fumantes or 0,
        }

    # ==========================================
    # MÉTODOS PRIVADOS DE REGRAS DE NEGÓCIO
    # ==========================================

    def _calcular_eficiencia_e_alertas(
        self,
        comodos_list: list[dict[str, Any]],
        telefones_list: list[dict[str, Any]],
        moradores_list: list[dict[str, Any]],
        saude_dict: dict[str, Any],
        total_ind: int,
    ) -> tuple[float, list[str]]:

        penalidades = 0.0
        pontos_atencao = []

        # Regra 1: Cômodos
        if (
            comodos_list
            and comodos_list[0]["percentual"] > self.LIMITE_COMODOS_PERCENTUAL
        ):
            penalidades += self.PENALIDADE_COMODOS
            pontos_atencao.append(
                f"Vício de digitação: {comodos_list[0]['percentual']}% das casas têm {comodos_list[0]['comodos']} cômodos."
            )

        # Regra 2: Telefones Clonados
        if telefones_list:
            maior_repeticao = telefones_list[0]["qtd"]
            if maior_repeticao > self.LIMITE_TELEFONES_CRITICO:
                penalidades += self.PENALIDADE_TELEFONES_CRITICO
                pontos_atencao.append(
                    f"Uso de contato clonado: telefone {telefones_list[0]['telefone']} usado em {maior_repeticao} cadastros."
                )
            elif maior_repeticao > self.LIMITE_TELEFONES_ATENCAO:
                penalidades += self.PENALIDADE_TELEFONES_ATENCAO
                pontos_atencao.append(
                    f"Duplicações de telefones identificadas (máximo de {maior_repeticao} munícipes com mesmo número)."
                )

        # Regra 3: Subnotificação Familiar
        casas_unipessoais_ou_nulas = sum(
            item["percentual"]
            for item in moradores_list
            if item["qtd_morador"] in (1, None)
        )
        if casas_unipessoais_ou_nulas > self.LIMITE_MORADORES_UNIPESSOAL:
            penalidades += self.PENALIDADE_MORADORES
            pontos_atencao.append(
                f"Subnotificação familiar: {casas_unipessoais_ou_nulas:.1f}% dos domicílios têm apenas 1 morador ou dado nulo."
            )

        # Regra 4: Subnotificação Epidemiológica
        if total_ind > 0:
            pct_hipertensao = (saude_dict["hipertensos"] / total_ind) * 100
            if pct_hipertensao < self.LIMITE_HIPERTENSAO_MINIMO:
                penalidades += self.PENALIDADE_HIPERTENSAO
                pontos_atencao.append(
                    f"Subnotificação de Hipertensão: apenas {pct_hipertensao:.1f}% declarados (esperado > 22%)."
                )

            if saude_dict["respiratoria"] == 0:
                penalidades += self.PENALIDADE_RESPIRATORIA
                pontos_atencao.append(
                    "Omissão total de Doenças Respiratórias (Asma/DPOC com 0 casos)."
                )

        taxa_eficiencia = max(0.0, round(100.0 - penalidades, 2))
        return taxa_eficiencia, pontos_atencao

    def _determinar_classificacao(self, taxa_eficiencia: float) -> str:
        if taxa_eficiencia >= 85.0:
            return "Conforme / Alta Qualidade"
        if taxa_eficiencia >= 70.0:
            return "Regular / Requer Revisão Amostral"
        if taxa_eficiencia >= 50.0:
            return "Inconsistente / Alinhamento Técnico"
        return "Crítica / Notificação Formal e Recadastramento"
