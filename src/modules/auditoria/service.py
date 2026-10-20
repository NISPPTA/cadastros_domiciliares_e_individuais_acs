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
    # --- Parâmetros e Limites de Auditoria ---
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

    # ==========================================
    # MÉTODOS PÚBLICOS DE CONSULTA GERAL
    # ==========================================

    async def listar_acs_ativos(
        self, esus_session: AsyncSession
    ) -> list[dict[str, Any]]:
        """Recupera todos os profissionais que atuam ativamente como ACS no e-SUS PEC."""
        query = text("""
            SELECT DISTINCT 
                dp.co_seq_dim_profissional AS id,
                dp.no_profissional AS nome,
                dp.nu_cns AS cns
            FROM tb_dim_profissional dp
            JOIN tb_fat_cad_domiciliar fd ON fd.co_dim_profissional = dp.co_seq_dim_profissional
            WHERE dp.no_profissional NOT ILIKE '%ADMINISTRADOR%'
              AND dp.no_profissional NOT ILIKE '%GESTOR%'
            ORDER BY dp.no_profissional ASC;
        """)
        result = await esus_session.execute(query)
        return [
            {"id": row.id, "nome": row.nome, "cns": row.cns} for row in result.all()
        ]

    async def buscar_acs_por_termo(
        self, esus_session: AsyncSession, termo: str, limit: int = 15
    ) -> list[dict[str, Any]]:
        """Pesquisa agentes em tempo real com base em parte do nome ou CNS."""
        query = text("""
            SELECT DISTINCT 
                dp.co_seq_dim_profissional AS id,
                dp.no_profissional AS nome,
                dp.nu_cns AS cns
            FROM tb_dim_profissional dp
            JOIN tb_fat_cad_domiciliar fd ON fd.co_dim_profissional = dp.co_seq_dim_profissional
            WHERE (dp.no_profissional ILIKE :termo OR dp.nu_cns ILIKE :termo)
              AND dp.no_profissional NOT ILIKE '%ADMINISTRADOR%'
              AND dp.no_profissional NOT ILIKE '%GESTOR%'
            ORDER BY dp.no_profissional ASC
            LIMIT :limit;
        """)
        termo_param = f"%{termo.strip()}%"
        result = await esus_session.execute(
            query, {"termo": termo_param, "limit": limit}
        )
        return [{"id": r.id, "nome": r.nome, "cns": r.cns} for r in result.all()]

    async def buscar_reversa_endereco(
        self, esus_session: AsyncSession, logradouro: str, numero: str | None = None
    ) -> list[dict[str, Any]]:
        """Busca qual ACS e Microárea são responsáveis por um determinado endereço."""

        query_base = """
            SELECT 
                fd.co_seq_fat_cad_domiciliar AS id_ficha,
                dp.co_seq_dim_profissional AS id_agente,
                dp.no_profissional AS agente_responsavel,
                dp.nu_cns AS cns_agente,
                COALESCE(fd.nu_micro_area, 'Sem Microárea') AS microarea,
                ccd.no_logradouro AS rua,
                ccd.nu_domicilio AS numero,
                ccd.no_bairro AS bairro,
                TO_CHAR(ccd.dt_cad_domiciliar, 'DD/MM/YYYY') AS data_cadastro
            FROM tb_cds_cad_domiciliar ccd
            JOIN tb_fat_cad_domiciliar fd ON fd.nu_uuid_ficha = ccd.co_unico_ficha
            JOIN tb_dim_profissional dp ON dp.co_seq_dim_profissional = fd.co_dim_profissional
            WHERE ccd.no_logradouro ILIKE :rua
        """
        params = {"rua": f"%{logradouro}%"}

        if numero and numero.strip():
            query_base += " AND ccd.nu_domicilio = :numero"
            params["numero"] = numero.strip()

        query_base += " ORDER BY ccd.dt_cad_domiciliar DESC;"

        result = await esus_session.execute(text(query_base), params)
        return [dict(row._mapping) for row in result.all()]

    async def buscar_logradouros_autocomplete(
        self, esus_session: AsyncSession, termo: str, limit: int = 10
    ) -> list[str]:
        """Busca nomes de ruas (distinct) para o autocomplete da busca reversa."""
        query = text("""
            SELECT DISTINCT no_logradouro
            FROM tb_cds_cad_domiciliar
            WHERE no_logradouro ILIKE :termo
              AND no_logradouro IS NOT NULL
            ORDER BY no_logradouro ASC
            LIMIT :limit;
        """)
        termo_param = f"%{termo.strip()}%"
        result = await esus_session.execute(
            query, {"termo": termo_param, "limit": limit}
        )
        return [row[0] for row in result.all()]

    async def auditar_acs(
        self, esus_session: AsyncSession, profissional_id: int
    ) -> RelatorioAuditoriaACS:
        """Executa a auditoria completa de um agente."""
        params = {"id": profissional_id}

        nome_acs = await self._buscar_nome_acs(esus_session, params)
        comodos_list = await self._buscar_comodos(esus_session, params)
        telefones_list = await self._buscar_telefones_duplicados(esus_session, params)
        moradores_list = await self._buscar_moradores(esus_session, params)
        saude_dict = await self._buscar_dados_saude(esus_session, params)

        total_domicilios = sum(item["total"] for item in comodos_list)
        total_ind = saude_dict["total_cadastros"]

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

    async def buscar_detalhes_ficha_domiciliar(
        self, esus_session: AsyncSession, id_ficha: int
    ) -> dict[str, Any] | None:
        """Busca os dados detalhados de saneamento e moradia da ficha domiciliar."""
        query_casa = text("""
            SELECT 
                fd.co_seq_fat_cad_domiciliar AS id_ficha,
                COALESCE(ccd.no_logradouro, 'Não Informado') AS rua,
                COALESCE(ccd.nu_domicilio, 'S/N') AS numero,
                COALESCE(ccd.no_bairro, '-') AS bairro,
                COALESCE(fd.nu_comodo, 0) AS qtd_comodos,
                COALESCE(fd.qt_morador, 0) AS qtd_moradores,
                
                COALESCE(daa.ds_tipo_abastecimento_agua, 'Não Informado') AS agua,
                COALESCE(dta.ds_tipo_tratamento_agua, 'Não Informado') AS tratamento_agua,
                COALESCE(des.ds_tipo_escoamento_sanitario, 'Não Informado') AS esgoto,
                COALESCE(ddl.ds_tipo_destino_lixo, 'Não Informado') AS lixo,
                
                CASE WHEN fd.st_animal_domiciliar = 1 
                     THEN 'Sim (' || COALESCE(fd.qt_animal_domiciliar, 0) || ' animal/is)' 
                     ELSE 'Não/Sem Animais' 
                END AS animais,
                
                TO_CHAR(ccd.dt_cad_domiciliar, 'DD/MM/YYYY') AS data_cadastro
            FROM tb_fat_cad_domiciliar fd
            LEFT JOIN tb_cds_cad_domiciliar ccd ON ccd.co_unico_ficha = fd.nu_uuid_ficha
            LEFT JOIN tb_dim_tipo_abastecimento_agua daa ON daa.co_seq_dim_tipo_abastec_agua = fd.co_dim_tipo_abastecimento_agua
            LEFT JOIN tb_dim_tipo_destino_lixo ddl ON ddl.co_seq_dim_tipo_destino_lixo = fd.co_dim_tipo_destino_lixo
            LEFT JOIN tb_dim_tipo_tratamento_agua dta ON dta.co_seq_dim_tipo_tratament_agua = fd.co_dim_tipo_tratamento_agua
            LEFT JOIN tb_dim_tipo_escoamento_sanitar des ON des.co_seq_dim_tipo_escoamento_snt = fd.co_dim_tipo_escoamento_sanitar
            WHERE fd.co_seq_fat_cad_domiciliar = :id_ficha;
        """)
        row_casa = (
            await esus_session.execute(query_casa, {"id_ficha": id_ficha})
        ).first()

        return dict(row_casa._mapping) if row_casa else None

    async def buscar_visitas_domicilio_paginado(
        self, esus_session: AsyncSession, id_ficha: int, limit: int = 5, offset: int = 0
    ) -> dict[str, Any]:
        """Busca o histórico de visitas agrupadas de um domicílio com suporte a paginação."""

        # 1. Conta o total de visitas únicas (agrupadas) para a paginação
        query_count = text("""
            WITH VisitasAgrupadas AS (
                SELECT vd.co_dim_tempo, vd.co_dim_desfecho_visita
                FROM tb_fat_familia_territorio ft
                JOIN tb_fat_visita_domiciliar vd ON vd.co_fat_cidadao_pec = ft.co_fat_cidadao_pec
                WHERE ft.co_fat_cad_domiciliar = :id_ficha
                GROUP BY vd.co_dim_tempo, vd.co_dim_desfecho_visita
            )
            SELECT COUNT(*) FROM VisitasAgrupadas;
        """)
        total = (
            await esus_session.execute(query_count, {"id_ficha": id_ficha})
        ).scalar() or 0

        # 2. Busca as visitas com LIMIT dinâmico e OFFSET
        query_visitas = text("""
            SELECT 
                t.nu_dia || '/' || t.nu_mes || '/' || t.nu_ano AS data_visita,
                COALESCE(ddv.ds_desfecho_visita, 'Não Informado') AS desfecho,
                COALESCE(MAX(vd.nu_medicao_pressao_arterial), '-') AS pressao,
                COALESCE(MAX(vd.nu_medicao_glicemia), '-') AS glicemia
            FROM tb_fat_familia_territorio ft
            JOIN tb_fat_visita_domiciliar vd ON vd.co_fat_cidadao_pec = ft.co_fat_cidadao_pec
            LEFT JOIN tb_dim_tempo t ON t.co_seq_dim_tempo = vd.co_dim_tempo
            LEFT JOIN tb_dim_desfecho_visita ddv ON ddv.co_seq_dim_desfecho_visita = vd.co_dim_desfecho_visita
            WHERE ft.co_fat_cad_domiciliar = :id_ficha
            GROUP BY vd.co_dim_tempo, t.nu_dia, t.nu_mes, t.nu_ano, ddv.ds_desfecho_visita
            ORDER BY vd.co_dim_tempo DESC
            LIMIT :limit OFFSET :offset;
        """)
        res_visitas = await esus_session.execute(
            query_visitas, {"id_ficha": id_ficha, "limit": limit, "offset": offset}
        )

        return {
            "total": total,
            "registros": [dict(v._mapping) for v in res_visitas.all()],
        }

    # ==========================================
    # MÉTODOS DA BANCADA PERICIAL (TELAS DETALHADAS)
    # ==========================================

    async def listar_domicilios_detalhado(
        self,
        esus_session: AsyncSession,
        profissional_id: int,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Lista paginada de domicílios priorizando o endereço decodificado da tabela CDS."""

        query_count = text(
            "SELECT COUNT(co_seq_fat_cad_domiciliar) FROM tb_fat_cad_domiciliar WHERE co_dim_profissional = :id"
        )
        total_records = (
            await esus_session.execute(query_count, {"id": profissional_id})
        ).scalar() or 0

        query = text("""
            SELECT 
                fd.co_seq_fat_cad_domiciliar AS id_ficha,
                CASE 
                    WHEN ccd.no_logradouro IS NOT NULL THEN ccd.no_logradouro
                    WHEN LENGTH(fd.no_logradouro) >= 32 THEN 'Rua Codificada (Verificar no Prontuário)'
                    ELSE COALESCE(fd.no_logradouro, 'Endereço Não Informado')
                END AS logradouro,
                CASE 
                    WHEN ccd.nu_domicilio IS NOT NULL THEN ccd.nu_domicilio
                    WHEN LENGTH(fd.nu_num_logradouro) >= 32 THEN 'S/N'
                    ELSE COALESCE(fd.nu_num_logradouro, 'S/N')
                END AS numero,
                CASE 
                    WHEN ccd.no_bairro IS NOT NULL THEN ccd.no_bairro
                    WHEN LENGTH(fd.no_bairro) >= 32 THEN 'Bairro Codificado'
                    ELSE COALESCE(fd.no_bairro, '-')
                END AS bairro,
                COALESCE(fd.nu_micro_area, '-') AS microarea,
                COALESCE(fd.nu_comodo, 0) AS qtd_comodos,
                COALESCE(fd.qt_morador, 0) AS qtd_moradores,
                CASE 
                    WHEN COALESCE(fd.qt_morador, 0) > 30 THEN 'Aberração: Lotação Extrema'
                    WHEN fd.nu_comodo = 4 AND COALESCE(fd.qt_morador, 0) <= 1 THEN 'Crítico: Vício + Subnotificação Familiar'
                    WHEN fd.nu_comodo = 4 THEN 'Alerta: 4 Cômodos'
                    WHEN COALESCE(fd.qt_morador, 0) = 0 THEN 'Crítico: Sem Moradores Declarados'
                    ELSE 'Regular'
                END AS status_auditoria
            FROM tb_fat_cad_domiciliar fd
            LEFT JOIN tb_cds_cad_domiciliar ccd ON ccd.co_unico_ficha = fd.nu_uuid_ficha
            WHERE fd.co_dim_profissional = :id
            ORDER BY fd.co_seq_fat_cad_domiciliar DESC
            LIMIT :limit OFFSET :offset;
        """)
        result = await esus_session.execute(
            query, {"id": profissional_id, "limit": limit, "offset": offset}
        )
        registros = [dict(row._mapping) for row in result.all()]

        return {"total": total_records, "registros": registros}

    async def listar_individuos_detalhado(
        self,
        esus_session: AsyncSession,
        profissional_id: int,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Lista paginada de munícipes com data/hora exata do tablet, nascimento e checagem clínica."""

        query_count = text(
            "SELECT COUNT(co_seq_fat_cad_individual) FROM tb_fat_cad_individual WHERE co_dim_profissional = :id"
        )
        total_records = (
            await esus_session.execute(query_count, {"id": profissional_id})
        ).scalar() or 0

        query = text("""
            SELECT 
                fi.co_seq_fat_cad_individual AS id_ficha,
                c.no_cidadao AS nome,
                COALESCE(c.nu_cpf, 'Sem CPF') AS cpf,
                TO_CHAR(c.dt_nascimento, 'DD/MM/YYYY') AS nascimento,
                TO_CHAR(cci.dt_cad_individual, 'DD/MM/YYYY HH24:MI:SS') AS data_hora_cadastro,
                COALESCE(c.nu_telefone_celular, c.nu_telefone_contato, '-') AS telefone,
                CASE WHEN fi.st_hipertensao_arterial::text IN ('1', 'true') THEN true ELSE false END AS hipertenso,
                CASE WHEN fi.st_diabete::text IN ('1', 'true') THEN true ELSE false END AS diabetico,
                CASE WHEN fi.st_doenca_respiratoria::text IN ('1', 'true') THEN true ELSE false END AS respiratoria,
                COUNT(fi.co_seq_fat_cad_individual) OVER(PARTITION BY c.nu_cpf) AS repeticoes_cpf
            FROM tb_fat_cad_individual fi
            JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = fi.co_fat_cidadao_pec
            JOIN tb_cidadao c ON c.co_seq_cidadao = fcp.co_cidadao
            LEFT JOIN tb_cds_cad_individual cci ON cci.co_unico_ficha = fi.nu_uuid_ficha
            WHERE fi.co_dim_profissional = :id
            ORDER BY repeticoes_cpf DESC, c.no_cidadao ASC
            LIMIT :limit OFFSET :offset;
        """)
        result = await esus_session.execute(
            query, {"id": profissional_id, "limit": limit, "offset": offset}
        )
        registros = [dict(row._mapping) for row in result.all()]

        return {"total": total_records, "registros": registros}

    async def listar_duplicidades_agente(
        self,
        esus_session: AsyncSession,
        profissional_id: int,
        limit: int = 10,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Retorna as duplicidades paginadas."""

        cte = """
            WITH BaseCidadao AS (
                SELECT 
                    fi.co_seq_fat_cad_individual AS id_ficha,
                    c.no_cidadao AS nome,
                    c.nu_cpf AS cpf,
                    c.nu_cns AS cns,
                    COALESCE(c.nu_telefone_celular, c.nu_telefone_contato, '-') AS telefone_usado,
                    dp.nu_cns AS cns_acs,
                    dp.no_profissional AS nome_acs
                FROM tb_fat_cad_individual fi
                JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = fi.co_fat_cidadao_pec
                JOIN tb_cidadao c ON c.co_seq_cidadao = fcp.co_cidadao
                JOIN tb_dim_profissional dp ON dp.co_seq_dim_profissional = fi.co_dim_profissional
                WHERE fi.co_dim_profissional = :id
            )
        """

        query_count = text(
            cte
            + """
            SELECT COUNT(*) FROM (
                SELECT 1 FROM BaseCidadao 
                GROUP BY nome, cpf, cns, cns_acs, nome_acs, telefone_usado 
                HAVING COUNT(id_ficha) > 1
            ) AS sub
        """
        )
        total_records = (
            await esus_session.execute(query_count, {"id": profissional_id})
        ).scalar() or 0

        query = text(
            cte
            + """
            SELECT 
                nome,
                cpf,
                COUNT(id_ficha) AS total_cadastros_gerados,
                STRING_AGG(id_ficha::text, ', ' ORDER BY id_ficha DESC) AS ids_fichas,
                MAX(id_ficha) AS id_ficha,
                telefone_usado,
                CASE 
                    WHEN cns = cns_acs OR nome_acs ILIKE nome THEN true 
                    ELSE false 
                END AS is_autocadastro
            FROM BaseCidadao
            GROUP BY nome, cpf, cns, cns_acs, nome_acs, telefone_usado
            HAVING COUNT(id_ficha) > 1
            ORDER BY total_cadastros_gerados DESC
            LIMIT :limit OFFSET :offset;
        """
        )
        result = await esus_session.execute(
            query, {"id": profissional_id, "limit": limit, "offset": offset}
        )
        registros = [dict(row._mapping) for row in result.all()]

        return {"total": total_records, "registros": registros}

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
        comodos_list: list,
        telefones_list: list,
        moradores_list: list,
        saude_dict: dict,
        total_ind: int,
    ) -> tuple[float, list[str]]:
        penalidades = 0.0
        pontos_atencao = []

        if (
            comodos_list
            and comodos_list[0]["percentual"] > self.LIMITE_COMODOS_PERCENTUAL
        ):
            penalidades += self.PENALIDADE_COMODOS
            pontos_atencao.append(
                f"Vício de digitação: {comodos_list[0]['percentual']}% das casas têm {comodos_list[0]['comodos']} cômodos."
            )

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

        return max(0.0, round(100.0 - penalidades, 2)), pontos_atencao

    def _determinar_classificacao(self, taxa_eficiencia: float) -> str:
        if taxa_eficiencia >= 85.0:
            return "Conforme / Alta Qualidade"
        if taxa_eficiencia >= 70.0:
            return "Regular / Requer Revisão Amostral"
        if taxa_eficiencia >= 50.0:
            return "Inconsistente / Alinhamento Técnico"
        return "Crítica / Notificação Formal e Recadastramento"

    async def buscar_informacoes_cidadao(
        self, esus_session: AsyncSession, id_ficha: int
    ) -> dict[str, Any] | None:
        """Busca os dados clínicos e sociodemográficos completos de uma ficha individual."""
        query = text("""
            SELECT 
                fi.co_seq_fat_cad_individual AS id_ficha,
                c.no_cidadao AS nome,
                COALESCE(c.nu_cpf, c.nu_cns, 'Sem Documento') AS documento,
                TO_CHAR(c.dt_nascimento, 'DD/MM/YYYY') AS nascimento,
                
                -- Dados Familiares
                CASE WHEN fi.st_responsavel_familiar = 1 THEN 'Sim' ELSE 'Não' END AS responsavel_familiar,
                COALESCE(fi.no_visita_familiar_parentesco, 'Responsável / Não Informado') AS parentesco,
                CASE WHEN fi.st_beneficio_bolsa_familia = 1 THEN 'Sim' ELSE 'Não' END AS recebe_bolsa_familia,
                
                -- Condições de Saúde (Doenças Crônicas)
                CASE WHEN fi.st_hipertensao_arterial = 1 THEN 'Sim' ELSE 'Não' END AS hipertenso,
                CASE WHEN fi.st_diabete = 1 THEN 'Sim' ELSE 'Não' END AS diabetico,
                CASE WHEN fi.st_doenca_cardiaca = 1 THEN 'Sim' ELSE 'Não' END AS doenca_cardiaca,
                CASE WHEN fi.st_infarto = 1 THEN 'Sim' ELSE 'Não' END AS teve_infarto,
                CASE WHEN fi.st_avc = 1 THEN 'Sim' ELSE 'Não' END AS teve_avc,
                CASE WHEN fi.st_doenca_respiratoria = 1 THEN 'Sim' ELSE 'Não' END AS doenca_respiratoria,
                CASE WHEN fi.st_cancer = 1 THEN 'Sim' ELSE 'Não' END AS tem_cancer,
                
                -- Hábitos e Situações
                CASE WHEN fi.st_fumante = 1 THEN 'Sim' ELSE 'Não' END AS fumante,
                CASE WHEN fi.st_alcool = 1 THEN 'Sim' ELSE 'Não' END AS usa_alcool,
                CASE WHEN fi.st_gestante = 1 THEN 'Sim' ELSE 'Não' END AS gestante,
                CASE WHEN fi.st_morador_rua = 1 THEN 'Sim' ELSE 'Não' END AS morador_rua
            FROM tb_fat_cad_individual fi
            JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = fi.co_fat_cidadao_pec
            JOIN tb_cidadao c ON c.co_seq_cidadao = fcp.co_cidadao
            WHERE fi.co_seq_fat_cad_individual = :id_ficha;
        """)
        row = (await esus_session.execute(query, {"id_ficha": id_ficha})).first()
        return dict(row._mapping) if row else None

    async def buscar_agendamentos_cidadao_paginado(
        self, esus_session: AsyncSession, id_ficha: int, limit: int = 5, offset: int = 0
    ) -> dict[str, Any]:
        """Busca o histórico de atendimentos clínicos reais de um munícipe na UBS."""
        query_count = text("""
            SELECT COUNT(fai.co_seq_fat_atd_ind)
            FROM tb_fat_cad_individual fi
            JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = fi.co_fat_cidadao_pec
            JOIN tb_fat_atendimento_individual fai ON fai.co_fat_cidadao_pec = fcp.co_seq_fat_cidadao_pec
            WHERE fi.co_seq_fat_cad_individual = :id_ficha;
        """)
        total = (
            await esus_session.execute(query_count, {"id_ficha": id_ficha})
        ).scalar() or 0

        query_atend = text("""
            SELECT 
                TO_CHAR(fai.dt_inicial_atendimento, 'DD/MM/YYYY HH24:MI') AS data_atendimento,
                COALESCE(dp.no_profissional, 'Não Informado') AS profissional,
                COALESCE(cbo.no_cbo, 'CBO Não Informado') AS tipo_profissional,
                CASE 
                    WHEN fai.nu_pressao_sistolica IS NOT NULL THEN fai.nu_pressao_sistolica || '/' || fai.nu_pressao_diastolica
                    ELSE '-'
                END AS pressao,
                COALESCE(CAST(fai.nu_peso AS VARCHAR), '-') AS peso
            FROM tb_fat_cad_individual fi
            JOIN tb_fat_cidadao_pec fcp ON fcp.co_seq_fat_cidadao_pec = fi.co_fat_cidadao_pec
            JOIN tb_fat_atendimento_individual fai ON fai.co_fat_cidadao_pec = fcp.co_seq_fat_cidadao_pec
            LEFT JOIN tb_dim_profissional dp ON dp.co_seq_dim_profissional = fai.co_dim_profissional_1
            LEFT JOIN tb_dim_cbo cbo ON cbo.co_seq_dim_cbo = fai.co_dim_cbo_1
            WHERE fi.co_seq_fat_cad_individual = :id_ficha
            ORDER BY fai.dt_inicial_atendimento DESC
            LIMIT :limit OFFSET :offset;
        """)
        res_atend = await esus_session.execute(
            query_atend, {"id_ficha": id_ficha, "limit": limit, "offset": offset}
        )

        return {
            "total": total,
            "registros": [dict(v._mapping) for v in res_atend.all()],
        }
