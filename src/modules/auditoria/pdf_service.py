import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.modules.auditoria.service import RelatorioAuditoriaACS


class AuditoriaPDFService:
    """
    Serviço de infraestrutura com Responsabilidade Única (SRP):
    Transformar um RelatorioAuditoriaACS em um arquivo binário PDF,
    alinhado ao Memorando de Inconsistências.
    """

    def __init__(self):
        self.estilos = getSampleStyleSheet()
        self.estilo_titulo = ParagraphStyle(
            name="TituloLaudo",
            parent=self.estilos["Heading1"],
            alignment=1,
            spaceAfter=15,
            fontSize=12,
        )
        self.estilo_texto = ParagraphStyle(
            name="TextoLaudo", parent=self.estilos["Normal"], fontSize=10, spaceAfter=8
        )
        self.estilo_alerta = ParagraphStyle(
            name="AlertaLaudo",
            parent=self.estilos["Normal"],
            fontSize=10,
            textColor=colors.darkred,
            spaceAfter=5,
            leftIndent=15,
        )
        self.estilo_bold = ParagraphStyle(
            name="TextoBold",
            parent=self.estilos["Normal"],
            fontSize=10,
            spaceAfter=8,
            fontName="Helvetica-Bold",
        )

    def gerar_laudo_pdf(self, relatorio: RelatorioAuditoriaACS) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40,
            title=f"Laudo_Auditoria_{relatorio.nome_acs.replace(' ', '_')}",
        )

        elementos = []
        self._construir_cabecalho(elementos, relatorio)
        self._construir_contexto_memorando(elementos)
        self._construir_respostas_auditoria(elementos, relatorio)
        self._construir_tabela_resumo(elementos, relatorio)
        self._construir_assinaturas(elementos, relatorio)

        doc.build(elementos)
        pdf_bytes = buffer.getvalue()
        buffer.close()

        return pdf_bytes

    def _construir_cabecalho(
        self, elementos: list, relatorio: RelatorioAuditoriaACS
    ) -> None:
        elementos.append(
            Paragraph(
                "<b>RELATÓRIO DE INCONSISTÊNCIAS NOS CADASTROS DOMICILIARES E INDIVIDUAIS</b>",
                self.estilo_titulo,
            )
        )
        elementos.append(Spacer(1, 10))
        elementos.append(
            Paragraph(
                "<b>Assunto:</b> Comunicação de inconsistências nos cadastros realizados pelo Agente Comunitário de Saúde.",
                self.estilo_texto,
            )
        )
        elementos.append(
            Paragraph(
                f"<b>Servidor Auditado:</b> {relatorio.nome_acs}", self.estilo_texto
            )
        )
        elementos.append(
            Paragraph(
                f"<b>Volume Auditado no e-SUS PEC:</b> {relatorio.total_domicilios} Domicílios e {relatorio.total_cadastros_individuais} Indivíduos",
                self.estilo_texto,
            )
        )
        elementos.append(Spacer(1, 15))

    def _construir_contexto_memorando(self, elementos: list) -> None:
        texto_intro = (
            "Por meio deste, apresentamos a extração de dados diretamente do banco oficial para garantir a "
            "qualidade, confiabilidade e completude das informações registradas na Atenção Primária à Saúde, "
            "em resposta aos 4 (quatro) pontos de verificação solicitados pelo Departamento:"
        )
        elementos.append(Paragraph(texto_intro, self.estilo_texto))
        elementos.append(Spacer(1, 10))

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
                msg = f"Inconsistência Confirmada: {maior_comodo['percentual']}% dos domicílios apresentam exatamente {maior_comodo['comodos']} cômodos, não representando a realidade habitacional."
                elementos.append(Paragraph(msg, self.estilo_alerta))
            else:
                elementos.append(
                    Paragraph(
                        "Distribuição de cômodos apresenta variância aceitável.",
                        self.estilo_texto,
                    )
                )
        elementos.append(Spacer(1, 10))

        # 2. Telefones
        elementos.append(
            Paragraph(
                "<b>2. Telefones de contato (Vínculo repetido/Agente):</b>",
                self.estilo_bold,
            )
        )
        if relatorio.telefones_duplicados:
            maior_tel = relatorio.telefones_duplicados[0]
            if maior_tel["qtd"] > 10:
                msg = f"Inconsistência Confirmada: O telefone {maior_tel['telefone']} está vinculado a {maior_tel['qtd']} cadastros distintos, inviabilizando a comunicação direta com os responsáveis."
                elementos.append(Paragraph(msg, self.estilo_alerta))
            else:
                elementos.append(
                    Paragraph(
                        "Não foram identificadas clonagens massivas de telefones.",
                        self.estilo_texto,
                    )
                )
        else:
            elementos.append(
                Paragraph("Sem repetições anômalas de contato.", self.estilo_texto)
            )
        elementos.append(Spacer(1, 10))

        # 3. Ausência de membros
        elementos.append(
            Paragraph(
                "<b>3. Ausência de membros da família (Composição):</b>",
                self.estilo_bold,
            )
        )
        casas_unipessoais = sum(
            item["percentual"]
            for item in relatorio.dados_moradores
            if item["qtd_morador"] in (1, None)
        )
        if casas_unipessoais > 50.0:
            msg = f"Inconsistência Confirmada: {casas_unipessoais:.1f}% dos cadastros domiciliares apresentam ausência de integrantes ou apenas 1 morador, indicando omissão do núcleo familiar."
            elementos.append(Paragraph(msg, self.estilo_alerta))
        else:
            elementos.append(
                Paragraph(
                    "Densidade familiar registrada está em conformidade demográfica.",
                    self.estilo_texto,
                )
            )
        elementos.append(Spacer(1, 10))

        # 4. Condições de Saúde
        elementos.append(
            Paragraph(
                "<b>4. Ausência de doenças e condições de saúde referidas:</b>",
                self.estilo_bold,
            )
        )
        pct_hipertensao = (
            relatorio.dados_saude["hipertensos"]
            / (relatorio.total_cadastros_individuais or 1)
        ) * 100
        if pct_hipertensao < 10.0 or relatorio.dados_saude["respiratoria"] == 0:
            msg = f"Inconsistência Confirmada: Omissão clínica sistêmica. Apenas {pct_hipertensao:.1f}% declarados hipertensos e {relatorio.dados_saude['respiratoria']} casos de doenças respiratórias registrados."
            elementos.append(Paragraph(msg, self.estilo_alerta))
        else:
            elementos.append(
                Paragraph(
                    "Levantamento epidemiológico apresenta preenchimento regular.",
                    self.estilo_texto,
                )
            )
        elementos.append(Spacer(1, 15))

    def _construir_tabela_resumo(
        self, elementos: list, relatorio: RelatorioAuditoriaACS
    ) -> None:
        elementos.append(
            Paragraph("<b>CONCLUSÃO DO PROCESSAMENTO:</b>", self.estilo_bold)
        )
        texto_conclusao = "As inconsistências descritas comprometem o planejamento das ações e a identificação de vulnerabilidades. Segue a nota final de eficiência extraída do banco:"
        elementos.append(Paragraph(texto_conclusao, self.estilo_texto))
        elementos.append(Spacer(1, 5))

        dados_tabela = [
            ["Métrica Final", "Resultado Sistema"],
            ["Índice de Qualidade Cadastral (IQC)", f"{relatorio.taxa_eficiencia}%"],
            ["Situação do Servidor", relatorio.classificacao],
        ]

        tabela = Table(dados_tabela, colWidths=[250, 200])
        tabela.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("BOTTOMPADDING", (0, 0), (-1, 0), 10),
                    ("GRID", (0, 0), (-1, -1), 1, colors.black),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica-Bold"),
                    (
                        "TEXTCOLOR",
                        (1, 1),
                        (1, 1),
                        colors.green if relatorio.taxa_eficiencia >= 80 else colors.red,
                    ),
                ]
            )
        )
        elementos.append(tabela)

    def _construir_assinaturas(
        self, elementos: list, relatorio: RelatorioAuditoriaACS
    ) -> None:
        elementos.append(Spacer(1, 40))
        elementos.append(
            Paragraph(
                "___________________________________________________________",
                ParagraphStyle(name="Linha", alignment=1),
            )
        )
        elementos.append(
            Paragraph(
                "Departamento de Atenção Básica",
                ParagraphStyle(name="Assinatura", alignment=1, fontSize=9),
            )
        )
