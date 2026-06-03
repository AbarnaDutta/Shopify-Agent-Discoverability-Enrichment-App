# app/integrations/email_clients/hostinger_mail.py
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from app.integrations.email_clients.email_interface import Email

class HostingerMail(Email):
    def __init__(self, sender_email: str, password: str) -> None:
        # Hostinger SMTP server configuration
        self.smtp_server = "smtp.hostinger.com"
        self.smtp_port = 587
        self.sender_email = sender_email
        self.password = password
        self.bcc_email    = os.getenv("ADMIN_EMAIL", "")

    def authenticate(self) -> None:
        # Hostinger SMTP does not require per-email authentication, so this is a no-op.
        pass

    def send_mail(self, recipient_email: str, subject: str, message_body: str, attachments: list | None = None) -> None:
        message = MIMEMultipart()
        message["Subject"] = subject
        message["From"]    = self.sender_email
        message["To"]      = recipient_email
        message.attach(MIMEText(message_body, "plain"))

        # Attach any provided files
        
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
                    part.add_header("Content-Disposition", f'attachment;filename="{filename}"')
                    message.attach(part)
                except Exception as e:
                    print(f"Warning: could not attach {attachment}: {e}")
        all_recipients = [recipient_email]
        if self.bcc_email:
            all_recipients.append(self.bcc_email)

        try:
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.password)
                server.sendmail(self.sender_email, all_recipients, message.as_string())
            print(f"Email sent to {recipient_email}")
        except Exception as e:
            print(f"Error sending email to {recipient_email}: {e}")
