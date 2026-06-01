from __future__ import annotations

from typing import Any

from app.integrations.email_clients.email_interface import Email
from app.services.report_builder import build_pdf_attachment

class EmailService:
    def __init__(self, email_client: Email) -> None:
        self.email_client = email_client

    @staticmethod
    def _build_report_email(store_url) -> tuple[str, str]:
        return (
            f"Your Shopify enrichment PDF report for {store_url} is ready. "
            "The PDF report is attached to this email."
        )

    @staticmethod
    def _build_failure_email(store_url: str) -> tuple[str, str]:
        lines = [
            f"We ran into an issue processing the store URL {store_url}.",
            "Please make sure the store URL is accurate.",
        ]
        lines.append("We are also looking into this on our end to see if there is a system issue.")
        return " ".join(lines)
    
    def send_report_email(self, recipient_email: str, report: dict[str, Any], products: list[dict[str, Any]], store_url: str) -> None:
        subject = f"Shopify enrichment report for {store_url}"
        text_body = self._build_report_email(store_url)
        try:
            pdf_bytes, pdf_filename = build_pdf_attachment(report, products, store_url)
        except RuntimeError as error:
            print(f"Error during pdf attachment creation: {error}")
            self.send_failure_email(recipient_email, store_url, error)
            return
        
        self.email_client.send_mail(recipient_email, subject, text_body, [(pdf_bytes, pdf_filename)])

    def send_failure_email(self, recipient_email: str, store_url: str, error: str) -> None:
        print(f"Error during report generation: {error}")
        failure_body = self._build_failure_email(store_url)
        subject = f"Shopify enrichment report for {store_url}"
        self.email_client.send_mail(recipient_email, subject, failure_body)
        return
        
