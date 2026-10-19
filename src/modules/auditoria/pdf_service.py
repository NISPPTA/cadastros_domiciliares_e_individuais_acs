import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.modules.auditoria.service import RelatorioAuditoriaACS


class AuditoriaPDFService:
    """
    Serviço de infraestrutura com Responsabilidade Única (SRP):
    Gera o laudo probatório em PDF perfeitamente diagramado para 1 página A4,
    com vocabulário ajustado e regras formatadas.
    """

    def __init__(self):
        self.estilos = getSampleStyleSheet()

        self.estilo_titulo = ParagraphStyle(
            name="TituloLaudo",
            parent=self.estilos["Heading1"],
            alignment=1,
            fontSize=10.5,
            leading=12.5,
            spaceAfter=3,
            textColor=colors.HexColor("#0f172a"),
            fontName="Helvetica-Bold",
        )
        self.estilo_texto = ParagraphStyle(
            name="TextoLaudo",
            parent=self.estilos["Normal"],
            fontSize=8,
            leading=10,
            spaceAfter=2,
            textColor=colors.HexColor("#334155"),
        )
        self.estilo_alerta = ParagraphStyle(
            name="AlertaLaudo",
            parent=self.estilos["Normal"],
            fontSize=8,
            leading=10,
            textColor=colors.HexColor("#991b1b"),
            spaceAfter=2,
            leftIndent=6,
        )
        self.estilo_bold = ParagraphStyle(
            name="TextoBold",
            parent=self.estilos["Normal"],
            fontSize=8,
            leading=10,
            spaceAfter=1,
            fontName="Helvetica-Bold",
            textColor=colors.HexColor("#0f172a"),
        )

    def gerar_laudo_pdf(self, relatorio: RelatorioAuditoriaACS) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=32,
            rightMargin=32,
            topMargin=22,
            bottomMargin=22,
            title=f"Laudo_Auditoria_{relatorio.nome_acs.replace(' ', '_')}",
        )

        elementos = []
        self._construir_cabecalho(elementos, relatorio)
        self._construir_contexto_memorando(elementos)
        self._construir_respostas_auditoria(elementos, relatorio)
        self._construir_tabela_resumo(elementos, relatorio)
        self._construir_matriz_regras(elementos)
        self._construir_assinaturas(elementos)

        doc.build(elementos)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

    def _construir_cabecalho(
        self, elementos: list, relatorio: RelatorioAuditoriaACS
    ) -> None:
        elementos.append(
            Paragraph(
                "<b>RELATÓRIO DE AUDITORIA E CONFERÊNCIA CADASTRAL NO e-SUS PEC</b>",
                self.estilo_titulo,
            )
        )
        elementos.append(
            Paragraph(
                "<b>Assunto:</b> Notificação de inconsistências cadastrais e parecer probatório técnico.",
                self.estilo_texto,
            )
        )
        elementos.append(
            Paragraph(
                f"<b>Servidor Auditado:</b> {relatorio.nome_acs} &nbsp;|&nbsp; <b>CBO:</b> Agente Comunitário de Saúde (ACS)",
                self.estilo_texto,
            )
        )
        elementos.append(
            Paragraph(
                f"<b>Base Auditada:</b> {relatorio.total_domicilios} Domicílios e {relatorio.total_cadastros_individuais} Cadastros Individuais extraídos diretamente do banco de dados.",
                self.estilo_texto,
            )
        )
        elementos.append(Spacer(1, 3))

    def _construir_contexto_memorando(self, elementos: list) -> None:
        # Removido o acento problemático de 'à' temporariamente para evitar falha do ReportLab
        texto_intro = (
            "Em atendimento a solicitação de verificação técnica, procedeu-se a validação automatizada da integridade "
            "dos registros em confronto com os parâmetros da Atenção Primária a Saúde, respondendo aos quatro pontos da comunicação:"
        )
        elementos.append(Paragraph(texto_intro, self.estilo_texto))
        elementos.append(Spacer(1, 3))

    def _construir_respostas_auditoria(
        self, elementos: list, relatorio: RelatorioAuditoriaACS
    ) -> None:
        # 1. Cômodos
        elementos.append(
            Paragraph(
                "<b>1. Informação sobre o número de cômodos (Uniformidade):</b>",
                self.estilo_bold,
            )
        )
        if relatorio.detalhes_comodos:
            maior_comodo = relatorio.detalhes_comodos[0]
            if maior_comodo["percentual"] > 70.0:
                msg = f"<b>Inconsistência Crítica:</b> {maior_comodo['percentual']}% dos domicílios foram registrados com exatamente {maior_comodo['comodos']} cômodos, evidenciando vício de preenchimento que oculta a real vulnerabilidade habitacional."
                elementos.append(Paragraph(msg, self.estilo_alerta))
            else:
                elementos.append(
                    Paragraph(
                        "Distribuição de cômodos apresenta dispersão regular e condizente.",
                        self.estilo_texto,
                    )
                )
        elementos.append(Spacer(1, 2))

        # 2. Telefones
        elementos.append(
            Paragraph(
                "<b>2. Telefones de contato (Comunicação e Vínculo ao Agente):</b>",
                self.estilo_bold,
            )
        )
        if relatorio.telefones_duplicados:
            maior_tel = relatorio.telefones_duplicados[0]
            if maior_tel["qtd"] > 10:
                msg = f"<b>Inconsistência Crítica:</b> O telefone {maior_tel['telefone']} encontra-se replicado em {maior_tel['qtd']} cadastros de munícipes distintos, inviabilizando o contato direto das equipes com os usuários."
                elementos.append(Paragraph(msg, self.estilo_alerta))
            else:
                elementos.append(
                    Paragraph(
                        "Não foram identificadas clonagens massivas de contatos.",
                        self.estilo_texto,
                    )
                )
        else:
            elementos.append(
                Paragraph(
                    "Sem repetições anômalas de contato telefônico.", self.estilo_texto
                )
            )
        elementos.append(Spacer(1, 2))

        # 3. Ausência de membros
        elementos.append(
            Paragraph(
                "<b>3. Ausência de membros da família (Composição e Densidade):</b>",
                self.estilo_bold,
            )
        )
        casas_unipessoais = sum(
            item["percentual"]
            for item in relatorio.dados_moradores
            if item["qtd_morador"] in (1, None)
        )
        if casas_unipessoais > 50.0:
            msg = f"<b>Inconsistência Crítica:</b> {casas_unipessoais:.1f}% das residências apresentam ausência de integrantes ou apenas 1 morador declarado, configurando subnotificação expressiva do núcleo familiar adscrito."
            elementos.append(Paragraph(msg, self.estilo_alerta))
        else:
            elementos.append(
                Paragraph(
                    "Densidade familiar registrada em conformidade demográfica.",
                    self.estilo_texto,
                )
            )
        elementos.append(Spacer(1, 2))

        # 4. Condições de Saúde
        elementos.append(
            Paragraph(
                "<b>4. Ausência de doenças e condições crônicas referidas (Subnotificação Clínica):</b>",
                self.estilo_bold,
            )
        )
        pct_hipertensao = (
            relatorio.dados_saude["hipertensos"]
            / (relatorio.total_cadastros_individuais or 1)
        ) * 100
        if pct_hipertensao < 10.0 or relatorio.dados_saude["respiratoria"] == 0:
            msg = f"<b>Inconsistência Crítica:</b> Apenas {pct_hipertensao:.1f}% possuem menção a Hipertensão Arterial (esperado acima de 22%) e registrou-se {relatorio.dados_saude['respiratoria']} casos de doenças respiratórias (Asma/DPOC), caracterizando grave omissão epidemiológica."
            elementos.append(Paragraph(msg, self.estilo_alerta))
        else:
            elementos.append(
                Paragraph(
                    "Levantamento epidemiológico apresenta preenchimento regular.",
                    self.estilo_texto,
                )
            )
        elementos.append(Spacer(1, 3))

    def _construir_tabela_resumo(
        self, elementos: list, relatorio: RelatorioAuditoriaACS
    ) -> None:
        elementos.append(
            Paragraph("<b>CONCLUSÃO TÉCNICA E ENQUADRAMENTO:</b>", self.estilo_bold)
        )

        dados_tabela = [
            ["Métrica de Integridade", "Resultado Apurado", "Parâmetro Regulatório"],
            [
                "Índice de Qualidade Cadastral (IQC)",
                f"{relatorio.taxa_eficiencia}%",
                "Mínimo Aceitável: 70.0%",
            ],
            [
                "Volume Auditado",
                f"{relatorio.total_domicilios} Dom. / {relatorio.total_cadastros_individuais} Indiv.",
                "Base Territorial Oficial",
            ],
            [
                "Enquadramento da Situação",
                relatorio.classificacao,
                "Instauração de PAD / Revisão",
            ],
        ]

        tabela = Table(dados_tabela, colWidths=[200, 165, 165])
        tabela.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTNAME", (1, 1), (1, 1), "Helvetica-Bold"),
                    ("FONTNAME", (1, 3), (1, 3), "Helvetica-Bold"),
                    (
                        "TEXTCOLOR",
                        (1, 1),
                        (1, 1),
                        colors.HexColor("#16a34a")
                        if relatorio.taxa_eficiencia >= 80
                        else colors.HexColor("#dc2626"),
                    ),
                    (
                        "TEXTCOLOR",
                        (1, 3),
                        (1, 3),
                        colors.HexColor("#16a34a")
                        if relatorio.taxa_eficiencia >= 80
                        else colors.HexColor("#dc2626"),
                    ),
                ]
            )
        )
        elementos.append(tabela)
        elementos.append(Spacer(1, 3))

    def _construir_matriz_regras(self, elementos: list) -> None:
        elementos.append(
            Paragraph(
                "<b>NOTA METODOLÓGICA E REGRAS DE PONTUAÇÃO (GESTÃO):</b>",
                self.estilo_bold,
            )
        )

        # Alargada a coluna de penalidade para não quebrar o texto
        dados_regras = [
            [
                "Pilar Auditado",
                "Critério de Conformidade (Tolerância)",
                "Penalidade no IQC",
            ],
            [
                "1. Cômodos",
                "Repetição da mesma quantidade de cômodos em até 70% dos domicílios",
                "-25.0% se concentração maior que 70%",
            ],
            [
                "2. Telefones",
                "Máximo de 10 cadastros com o mesmo telefone de contato",
                "-15.0% (11 a 50) | -25.0% (acima de 50)",
            ],
            [
                "3. Famílias",
                "Casas unipessoais ou com dados nulos em até 50% dos domicílios",
                "-20.0% se concentração maior que 50%",
            ],
            [
                "4. Saúde Crônica",
                "Hipertensão referida em 10% (esperado acima de 22%) e 1 caso respiratório",
                "-15.0% (Hipertensão < 10%) | -10.0% (0 respiratórias)",
            ],
            [
                "Enquadramento",
                "IQC >= 85%: Conforme | 70 a 84.9%: Regular | 50 a 69.9%: Inconsistente | < 50%: Crítica (PAD)",
                "Base de cálculo: 100.0% decrescente",
            ],
        ]

        tabela_regras = Table(dados_regras, colWidths=[80, 300, 150])
        tabela_regras.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("FONTSIZE", (0, 0), (-1, -1), 6.5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
                    ("TOPPADDING", (0, 0), (-1, -1), 1.5),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                    ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
                    ("TEXTCOLOR", (2, 1), (2, -1), colors.HexColor("#991b1b")),
                ]
            )
        )
        elementos.append(tabela_regras)

    def _construir_assinaturas(self, elementos: list) -> None:
        elementos.append(Spacer(1, 8))
        elementos.append(
            Paragraph(
                "___________________________________________________________",
                ParagraphStyle(name="Linha", alignment=1, fontSize=7.5, leading=8.5),
            )
        )
        elementos.append(
            Paragraph(
                "Comissão Municipal de Auditoria e Gestão da Informação em Saúde",
                ParagraphStyle(
                    name="Assinatura",
                    alignment=1,
                    fontSize=7.5,
                    leading=9,
                    fontName="Helvetica-Bold",
                ),
            )
        )
        elementos.append(
            Paragraph(
                "Secretaria Municipal de Saúde de Paraguaçu Paulista - SP",
                ParagraphStyle(
                    name="Org",
                    alignment=1,
                    fontSize=7,
                    leading=8,
                    textColor=colors.HexColor("#64748b"),
                ),
            )
        )
