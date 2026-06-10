# app/services/email_service.py
from __future__ import annotations

from typing import Any

from app.integrations.email_clients.email_interface import Email
from app.services.report_builder import build_pdf_attachment
_HINTS: dict[str, str] = {
    "invalid_store_url":  "Double-check the URL and make sure it includes the full domain, e.g. your-store.myshopify.com",
    "non_shopify_store":  "Confirm the store is built on Shopify and that the URL points to the storefront.",
    "store_unreachable":  "Check that the store is live and publicly accessible, then try again.",
    "llm_quota_exceeded": "This is a temporary provider limit. Please wait a few hours and resubmit.",
    "llm_rate_limited":   "Please wait a few minutes before resubmitting.",
    "llm_response_error": "This is usually temporary. Please try again — if it keeps happening, contact support.",
    "llm_auth_error":     "This is a configuration issue on our end. Please try again later.",
    "internal_error":     "Please try again later or contact us at propero.in",
    "non_shopify_store": (
        "Confirm the store is built on Shopify and publicly accessible. "
        "If the store uses Cloudflare bot protection, the owner may need to "
        "allow automated access to /products.json, or try a different store URL."
    ),
}


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

_FAILURE_TEMPLATES: dict[str, dict[str, str]] = {
    "English": {
        "subject": "We couldn't generate your Propero report — {store_url}",
        "greeting": "Hi there,",
        "intro": "We're sorry — we ran into an issue generating your AI Agent Discoverability Report for {store_url}.",
        "reason_label": "What went wrong:",
        "next_label": "What to do next:",
        "closing": "If the problem continues, feel free to reach out at propero.in and we'll help you out.",
        "sign_off": "The Propero Team\npropero.in",
    },
    "German": {
        "subject": "Ihr Propero-Bericht konnte nicht erstellt werden — {store_url}",
        "greeting": "Hallo,",
        "intro": "Es tut uns leid — beim Erstellen Ihres KI-Agenten-Berichts für {store_url} ist ein Fehler aufgetreten.",
        "reason_label": "Was ist passiert:",
        "next_label": "Was Sie als Nächstes tun können:",
        "closing": "Wenn das Problem weiterhin besteht, wenden Sie sich an propero.in und wir helfen Ihnen.",
        "sign_off": "Das Propero-Team\npropero.in",
    },
    "French": {
        "subject": "Nous n'avons pas pu générer votre rapport Propero — {store_url}",
        "greeting": "Bonjour,",
        "intro": "Nous sommes désolés — un problème est survenu lors de la génération de votre rapport pour {store_url}.",
        "reason_label": "Ce qui s'est passé :",
        "next_label": "Que faire ensuite :",
        "closing": "Si le problème persiste, contactez-nous sur propero.in et nous vous aiderons.",
        "sign_off": "L'équipe Propero\npropero.in",
    },
    "Spanish": {
        "subject": "No pudimos generar su informe Propero — {store_url}",
        "greeting": "Hola,",
        "intro": "Lo sentimos — ocurrió un problema al generar su informe para {store_url}.",
        "reason_label": "Qué ocurrió:",
        "next_label": "Qué hacer a continuación:",
        "closing": "Si el problema continúa, contáctenos en propero.in y le ayudaremos.",
        "sign_off": "El equipo de Propero\npropero.in",
    },
    "Italian": {
        "subject": "Non siamo riusciti a generare il tuo report Propero — {store_url}",
        "greeting": "Salve,",
        "intro": "Ci dispiace — si è verificato un problema durante la generazione del report per {store_url}.",
        "reason_label": "Cosa è successo:",
        "next_label": "Cosa fare:",
        "closing": "Se il problema persiste, contattaci su propero.in e ti aiuteremo.",
        "sign_off": "Il team Propero\npropero.in",
    },
    "Portuguese": {
        "subject": "Não conseguimos gerar seu relatório Propero — {store_url}",
        "greeting": "Olá,",
        "intro": "Lamentamos — ocorreu um problema ao gerar seu relatório para {store_url}.",
        "reason_label": "O que aconteceu:",
        "next_label": "O que fazer a seguir:",
        "closing": "Se o problema persistir, entre em contato em propero.in e iremos ajudá-lo.",
        "sign_off": "A equipe Propero\npropero.in",
    },
    "Dutch": {
        "subject": "We konden uw Propero-rapport niet genereren — {store_url}",
        "greeting": "Hallo,",
        "intro": "Het spijt ons — er is een probleem opgetreden bij het genereren van uw rapport voor {store_url}.",
        "reason_label": "Wat er is misgegaan:",
        "next_label": "Wat u kunt doen:",
        "closing": "Als het probleem aanhoudt, neem dan contact op via propero.in en we helpen u.",
        "sign_off": "Het Propero-team\npropero.in",
    },
    "Japanese": {
        "subject": "Properoレポートを生成できませんでした — {store_url}",
        "greeting": "こんにちは、",
        "intro": "{store_url}のAIエージェントレポート生成中に問題が発生しました。申し訳ございません。",
        "reason_label": "発生した問題：",
        "next_label": "次のステップ：",
        "closing": "問題が続く場合は、propero.in までお問い合わせください。",
        "sign_off": "Properoチーム\npropero.in",
    },
    "Chinese": {
        "subject": "我们无法生成您的Propero报告 — {store_url}",
        "greeting": "您好，",
        "intro": "很抱歉 — 为{store_url}生成AI代理报告时遇到了问题。",
        "reason_label": "发生了什么：",
        "next_label": "接下来怎么做：",
        "closing": "如果问题仍然存在，请通过 propero.in 联系我们，我们将为您提供帮助。",
        "sign_off": "Propero团队\npropero.in",
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

    @staticmethod
    def _build_failure_body(
        store_url: str,
        user_message: str,
        error_type: str,
        language: str,
    ) -> tuple[str, str]:
        t = EmailService._get_template(_FAILURE_TEMPLATES, language)
        hint = _HINTS.get(error_type, _HINTS["internal_error"])
        subject = t["subject"].format(store_url=store_url)
        body = "\n\n".join([
            t["greeting"],
            t["intro"].format(store_url=store_url),
            f"{t['reason_label']}\n{user_message}",
            f"{t['next_label']}\n{hint}",
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
        try:
            pdf_bytes, pdf_filename = build_pdf_attachment(
                report, products, store_url, language
            )
        except RuntimeError as error:
            self.send_failure_email(
                recipient_email, store_url,
                str(error), error_type="internal_error", language=language,
            )
            return
        self.email_client.send_mail(
            recipient_email, subject, body, [(pdf_bytes, pdf_filename)]
        )

    def send_failure_email(
        self,
        recipient_email: str,
        store_url: str,
        user_message: str,
        error_type: str = "internal_error",
        language: str = "English",
    ) -> None:
        subject, body = self._build_failure_body(
            store_url, user_message, error_type, language
        )
        self.email_client.send_mail(recipient_email, subject, body)