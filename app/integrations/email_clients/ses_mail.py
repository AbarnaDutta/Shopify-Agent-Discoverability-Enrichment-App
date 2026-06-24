# app/integrations/email_clients/ses_mail.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from app.integrations.email_clients.email_interface import Email


class SESMail(Email):
    def __init__(self, sender_email: str, smtp_username: str, smtp_password: str) -> None:
        self.sender_email  = sender_email
        self.smtp_username = smtp_username
        self.smtp_password = smtp_password
        self.smtp_server   = os.getenv("SES_SMTP_HOST", "email-smtp.ap-south-1.amazonaws.com")
        self.smtp_port     = int(os.getenv("SES_SMTP_PORT", "587"))
        self.bcc_email     = os.getenv("ADMIN_EMAIL", "")

    def authenticate(self) -> None:
        pass  

    def send_mail(
        self,
        recipient_email: str,
        subject: str,
        message_body: str,
        attachments: list | None = None,
    ) -> None:
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"]    = self.sender_email
        message["To"]      = recipient_email

        html_body = self._to_html(message_body)
        alt_part = MIMEMultipart("alternative")
        alt_part.attach(MIMEText(message_body, "plain", "utf-8"))
        alt_part.attach(MIMEText(html_body,    "html",  "utf-8"))
        message.attach(alt_part)

        if attachments:
            for attachment in attachments:
                try:
                    if isinstance(attachment, tuple) and len(attachment) == 2:
                        content, filename = attachment
                        part = MIMEBase("application", "octet-stream")
                        if isinstance(content, str):
                            content = content.encode("utf-8")
                        part.set_payload(content)
                    else:
                        path = Path(attachment)
                        with path.open("rb") as f:
                            part = MIMEBase("application", "octet-stream")
                            part.set_payload(f.read())
                        filename = path.name
                    encoders.encode_base64(part)
                    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
                    message.attach(part)
                except Exception as e:
                    print(f"Warning: could not attach {attachment}: {e}")

        all_recipients = [recipient_email]
        if self.bcc_email:
            all_recipients.append(self.bcc_email)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_username, self.smtp_password)
                server.sendmail(self.sender_email, all_recipients, message.as_string())
            print(f"Email sent via SES SMTP to {recipient_email}")
        except Exception as e:
            print(f"Error sending email via SES SMTP to {recipient_email}: {e}")
            raise

    @staticmethod
    def _to_html(text: str) -> str:
        import html as html_module
        lines = text.split("\n")
        html_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("—" * 5):
                html_lines.append('<hr style="border:none;border-top:1px solid #e0ddd6;margin:16px 0">')
            elif stripped == "":
                html_lines.append("<br>")
            elif stripped.startswith("  •"):
                item = html_module.escape(stripped[3:].strip())
                html_lines.append(f'<li style="margin-bottom:4px">{item}</li>')
            else:
                html_lines.append(
                    f'<p style="margin:0 0 8px;color:#333">{html_module.escape(stripped)}</p>'
                )

        result = []
        in_list = False
        for line in html_lines:
            if line.startswith("<li"):
                if not in_list:
                    result.append('<ul style="margin:8px 0 8px 20px;padding:0;color:#333">')
                    in_list = True
            else:
                if in_list:
                    result.append("</ul>")
                    in_list = False
            result.append(line)
        if in_list:
            result.append("</ul>")

        body_content = "\n".join(result)
        return f"""
        <html><body style="font-family:Arial,Helvetica,sans-serif;font-size:14px;
                        line-height:1.6;color:#333;max-width:600px;margin:0 auto;padding:24px">
        {body_content}
        <div style="margin-top:24px;padding-top:16px;border-top:1px solid #e0ddd6;
                    font-size:12px;color:#888">
            <a href="https://www.propero.in" style="color:#17695b;text-decoration:none">
            propero.in
            </a>
        </div>
        </body></html>
        """