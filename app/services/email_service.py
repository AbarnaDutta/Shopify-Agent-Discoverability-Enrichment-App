# app/services/email_service.py
from __future__ import annotations

from typing import Any

from app.integrations.email_clients.email_interface import Email
from app.services.report_builder import build_pdf_attachment

_EMAIL_BODY_TEMPLATES: dict[str, dict[str, str]] = {
    "English": {
        "subject":  "Your Propero AI Agent Readiness Report — {store_url}",
        "greeting": "Hi there,",
        "intro":    "Thank you for using Propero. Your AI Agent Discoverability Report for {store_url} is ready.",
        "body":     (
            "The report includes:\n"
            "  • Store-level recommendations to improve how AI agents discover your products\n"
            "  • Product-by-product analysis with prioritised enrichment suggestions\n"
            "  • An executive summary highlighting your biggest opportunities\n"
        ),
        "pdf_line": "Your report is attached as a PDF below.",
        "closing":  "If you have any questions, reply to this email or visit us at propero.in",
        "sign_off": "The Propero Team\npropero.in",
    },
    "German": {
        "subject":  "Ihr Propero KI-Agenten-Bereitschaftsbericht — {store_url}",
        "greeting": "Hallo,",
        "intro":    "Vielen Dank, dass Sie Propero nutzen. Ihr KI-Agenten-Auffindbarkeits-Bericht für {store_url} ist fertig.",
        "body":     (
            "Der Bericht enthält:\n"
            "  • Shop-weite Empfehlungen zur Verbesserung der Auffindbarkeit durch KI-Agenten\n"
            "  • Produkt-für-Produkt-Analyse mit priorisierten Anreicherungsvorschlägen\n"
            "  • Eine Zusammenfassung mit Ihren größten Chancen\n"
        ),
        "pdf_line": "Ihr Bericht ist als PDF unten beigefügt.",
        "closing":  "Bei Fragen antworten Sie auf diese E-Mail oder besuchen Sie uns unter propero.in",
        "sign_off": "Das Propero-Team\npropero.in",
    },
    "French": {
        "subject":  "Votre rapport Propero de préparation aux agents IA — {store_url}",
        "greeting": "Bonjour,",
        "intro":    "Merci d'utiliser Propero. Votre rapport de découvrabilité pour agents IA concernant {store_url} est prêt.",
        "body":     (
            "Le rapport comprend :\n"
            "  • Des recommandations au niveau boutique pour améliorer la découverte par les agents IA\n"
            "  • Une analyse produit par produit avec des suggestions d'enrichissement priorisées\n"
            "  • Un résumé exécutif mettant en avant vos meilleures opportunités\n"
        ),
        "pdf_line": "Votre rapport est joint en PDF ci-dessous.",
        "closing":  "Pour toute question, répondez à cet e-mail ou visitez propero.in",
        "sign_off": "L'équipe Propero\npropero.in",
    },
    "Spanish": {
        "subject":  "Su informe Propero de preparación para agentes IA — {store_url}",
        "greeting": "Hola,",
        "intro":    "Gracias por usar Propero. Su informe de descubribilidad para agentes IA de {store_url} está listo.",
        "body":     (
            "El informe incluye:\n"
            "  • Recomendaciones a nivel de tienda para mejorar cómo los agentes IA descubren sus productos\n"
            "  • Análisis producto a producto con sugerencias de enriquecimiento priorizadas\n"
            "  • Un resumen ejecutivo con sus mayores oportunidades\n"
        ),
        "pdf_line": "Su informe está adjunto como PDF a continuación.",
        "closing":  "Si tiene preguntas, responda a este correo o visítenos en propero.in",
        "sign_off": "El equipo de Propero\npropero.in",
    },
    "Japanese": {
        "subject":  "Propero AIエージェント対応レポート — {store_url}",
        "greeting": "こんにちは、",
        "intro":    "Properoをご利用いただきありがとうございます。{store_url}のAIエージェント発見可能性レポートが完成しました。",
        "body":     (
            "レポートには以下が含まれます：\n"
            "  • AIエージェントによる商品発見を改善するためのストアレベルの推薦事項\n"
            "  • 優先度付きの改善提案を含む商品ごとの分析\n"
            "  • 最大の機会を強調したエグゼクティブサマリー\n"
        ),
        "pdf_line": "レポートはPDFとして下に添付されています。",
        "closing":  "ご質問はこのメールへの返信、またはpropero.inまでお問い合わせください。",
        "sign_off": "Properoチーム\npropero.in",
    },
}


class EmailService:
    def __init__(self, email_client: Email) -> None:
        self.email_client = email_client

    @staticmethod
    def _get_template(templates: dict, language: str) -> dict:
        return templates.get(language, templates["English"])

    @staticmethod
    def _build_report_body(store_url: str, language: str) -> tuple[str, str]:
        t = EmailService._get_template(_EMAIL_BODY_TEMPLATES, language)
        subject = t["subject"].format(store_url=store_url)
        body = "\n\n".join([
            t["greeting"],
            t["intro"].format(store_url=store_url),
            t["body"],
            "—" * 40,
            t["pdf_line"],
            "—" * 40,
            t["closing"],
            t["sign_off"],
        ])
        return subject, body

    def send_report_email(
        self,
        recipient_email: str,
        report: dict,
        products: list,
        store_url: str,
        language: str = "English",
    ) -> None:
        subject, body = self._build_report_body(store_url, language)
        pdf_bytes, pdf_filename = build_pdf_attachment(
            report, products, store_url, language
        )
        self.email_client.send_mail(
            recipient_email, subject, body, [(pdf_bytes, pdf_filename)]
        )