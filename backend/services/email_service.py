"""
PR 26 — Email service scaffold.

Минимально жизнеспособный SMTP-клиент для:
- Password reset link
- Email confirmation
- Security alerts (например: «новый login с IP X»)

Принципы:
- Через стандартный smtplib (без зависимостей; готов к Yandex/Mailgun/SES)
- Если SMTP_HOST не настроен → log-only mode (дев-режим)
- НИКОГДА не падаем — email отправка не должна блокировать main flow
- Все письма HTML + plaintext fallback
- Best-effort через asyncio.to_thread, чтобы не блокировать event loop
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from typing import Optional

from config import settings
from logger import get_logger

log = get_logger("email")


def _is_configured() -> bool:
    """SMTP считается настроенным если есть host + from_addr."""
    return bool(getattr(settings, "SMTP_HOST", None)) and bool(
        getattr(settings, "EMAIL_FROM", None)
    )


def _send_sync(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Синхронная отправка через smtplib. Возвращает True если ушло."""
    if not _is_configured():
        log.warning(
            "email NOT sent (SMTP not configured): to=%s subject=%s",
            to_email,
            subject,
        )
        return False

    try:
        msg = EmailMessage()
        msg["From"] = settings.EMAIL_FROM
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body_text)
        if body_html:
            msg.add_alternative(body_html, subtype="html")

        host = settings.SMTP_HOST
        port = int(getattr(settings, "SMTP_PORT", 587))
        username = getattr(settings, "SMTP_USERNAME", None)
        password = getattr(settings, "SMTP_PASSWORD", None)
        use_tls = bool(getattr(settings, "SMTP_USE_TLS", True))

        if use_tls:
            with smtplib.SMTP(host, port, timeout=15) as smtp:
                smtp.starttls()
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15) as smtp:
                if username and password:
                    smtp.login(username, password)
                smtp.send_message(msg)

        log.info("email sent: to=%s subject=%s", to_email, subject)
        return True
    except Exception:
        log.exception(
            "email send failed: to=%s subject=%s (non-blocking)",
            to_email,
            subject,
        )
        return False


async def send_email(
    *,
    to_email: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
) -> bool:
    """Async обёртка — НЕ блокирует event loop."""
    return await asyncio.to_thread(
        _send_sync,
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )


def send_email_verification(to_email: str, verify_url: str, *, user_name: Optional[str] = None) -> bool:
    """PR 26 Phase 3: письмо для подтверждения email при регистрации."""
    greeting = f"Здравствуйте, {user_name}!" if user_name else "Здравствуйте!"
    subject = "Полистата — подтверждение email"
    body_text = (
        f"{greeting}\n\n"
        f"Спасибо за регистрацию в Полистата.\n\n"
        f"Подтвердите ваш email, перейдя по ссылке (действует 24 часа):\n"
        f"{verify_url}\n\n"
        f"Если это были не вы — игнорируйте письмо.\n\n"
        f"— Команда Полистата"
    )
    body_html = (
        f"<p>{greeting}</p>"
        f"<p>Спасибо за регистрацию в Полистата.</p>"
        f"<p><a href=\"{verify_url}\" style=\"background:#4f46e5;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;\">Подтвердить email</a></p>"
        f"<p style=\"color:#666;font-size:12px\">Ссылка действительна 24 часа. Если это были не вы — игнорируйте письмо.</p>"
        f"<p style=\"color:#999;font-size:11px\">— Команда Полистата</p>"
    )
    return _send_sync(to_email=to_email, subject=subject, body_text=body_text, body_html=body_html)


def send_already_registered_notice(to_email: str, reset_url: str) -> bool:
    """PR 26 Phase 3: при попытке зарегистрироваться с уже занятым email
    отправляем «вы уже зарегистрированы — вот ссылка для сброса пароля».

    Это закрывает enumeration: атакующий получает одинаковый 202 как для
    нового email, так и для существующего."""
    subject = "Полистата — попытка регистрации"
    body_text = (
        f"Кто-то попытался зарегистрироваться в Полистата с вашим email.\n\n"
        f"У вас уже есть аккаунт. Если забыли пароль, сбросьте по ссылке:\n"
        f"{reset_url}\n\n"
        f"Если это были не вы — просто игнорируйте.\n\n"
        f"— Команда Полистата"
    )
    return _send_sync(to_email=to_email, subject=subject, body_text=body_text)


def send_password_reset_email(
    to_email: str,
    reset_url: str,
    *,
    user_name: Optional[str] = None,
) -> bool:
    """Sync helper для password reset email.

    Письмо содержит ссылку с one-time token. Истекает через 1 час.
    """
    greeting = f"Здравствуйте, {user_name}!" if user_name else "Здравствуйте!"
    subject = "Полистата — сброс пароля"
    body_text = (
        f"{greeting}\n\n"
        f"Кто-то запросил сброс пароля для вашего аккаунта Полистата.\n\n"
        f"Перейдите по ссылке (действительна 1 час):\n"
        f"{reset_url}\n\n"
        f"Если это были не вы — просто игнорируйте письмо.\n\n"
        f"— Команда Полистата"
    )
    body_html = (
        f"<p>{greeting}</p>"
        f"<p>Кто-то запросил сброс пароля для вашего аккаунта Полистата.</p>"
        f"<p>"
        f"<a href=\"{reset_url}\" style=\"background:#4f46e5;color:#fff;"
        f"padding:10px 20px;border-radius:6px;text-decoration:none;\">"
        f"Установить новый пароль</a>"
        f"</p>"
        f"<p style=\"color:#666;font-size:12px\">Ссылка действительна 1 час. "
        f"Если это были не вы — просто игнорируйте письмо.</p>"
        f"<p style=\"color:#999;font-size:11px\">— Команда Полистата</p>"
    )
    return _send_sync(
        to_email=to_email,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
