# app/services/email_service.py
from __future__ import annotations

from typing import Any

from app.integrations.email_clients.email_interface import Email
from app.services.report_builder import build_pdf_attachment
_HINTS: dict[str, str] = {
    "invalid_store_url": (
        "Double-check the URL and make sure it includes the full domain, "
        "e.g. https://your-store.myshopify.com."
    ),
    "non_shopify_store": (
        "Confirm the store is built on Shopify and that the URL points to the "
        "storefront (not an admin or third-party page)."
    ),
    "store_unreachable": (
        "Check that the store is live and publicly accessible, then try again."
    ),
    "llm_quota_exceeded": (
        "This is a temporary provider limit. Please wait a few hours and resubmit."
    ),
    "llm_rate_limited": (
        "Please wait a few minutes before resubmitting."
    ),
    "llm_response_error": (
        "This is usually temporary. Please try again — if it keeps happening, "
        "contact support with your job ID."
    ),
    "llm_auth_error": (
        "This is a configuration issue on our end, not with your store. "
        "Please try again in a few minutes or contact support."
    ),
    "internal_error": (
        "Our team has been notified. Please try again later or contact support."
    ),
}


class EmailService:
    def __init__(self, email_client: Email) -> None:
        self.email_client = email_client

    @staticmethod
    def _build_report_email(store_url: str) -> str:
        return (
            f"Your Shopify AI Agent Discoverability Report for {store_url} is ready. "
            "Please find the PDF attached to this email."
        )

    @staticmethod
    def build_failure_email(store_url: str, user_message: str, error_type: str) -> str:
        hint = _HINTS.get(error_type, _HINTS["internal_error"])
        lines = [
            f"We were unable to generate a report for {store_url}.",
            "",
            f"Reason: {user_message}",
            "",
            f"What to do next: {hint}",
            "",
            "If you continue to experience issues, please contact support.",
        ]
        return "\n".join(lines)

    def send_report_email(
        self,
        recipient_email: str,
        report: dict[str, Any],
        products: list[dict[str, Any]],
        store_url: str,
        language: str = "English",       
    ) -> None:
        subject = f"Your AI Agent Discoverability Report — {store_url}"
        body = self._build_report_email(store_url)
        try:
            pdf_bytes, pdf_filename = build_pdf_attachment(
                report, products, store_url, language   
            )
        except RuntimeError as error:
            print(f"Error during pdf attachment creation: {error}")
            self.send_failure_email(
                recipient_email, store_url,
                str(error), error_type="internal_error",
            )
            return
        self.email_client.send_mail(
            recipient_email, subject, body, [(pdf_bytes, pdf_filename)]
        )
    def send_failure_email(self, recipient_email: str, store_url: str, user_message: str, error_type: str = "internal_error") -> None:
        print(f"Error during report generation: {error_type}")
        body = self.build_failure_email(store_url, user_message, error_type)
        subject = f"Report request failed — {store_url}"
        self.email_client.send_mail(recipient_email, subject, body)
        