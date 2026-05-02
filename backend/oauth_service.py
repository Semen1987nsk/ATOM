"""
OAuth Service - авторизация через внешние провайдеры
Google, Яндекс, Сбер ID, Тинькофф ID
"""

import os
import httpx
from typing import Optional
from urllib.parse import urlencode
from dataclasses import dataclass
from config import settings

# OAuth Provider Configuration
@dataclass
class OAuthProvider:
    name: str
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str
    
    def get_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
        }
        return f"{self.authorize_url}?{urlencode(params)}"


# Provider configurations
PROVIDERS = {}

# Google OAuth
if os.getenv("GOOGLE_CLIENT_ID"):
    PROVIDERS["google"] = OAuthProvider(
        name="Google",
        client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET", ""),
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        userinfo_url="https://www.googleapis.com/oauth2/v2/userinfo",
        scope="openid email profile",
    )

# Yandex OAuth
if os.getenv("YANDEX_CLIENT_ID"):
    PROVIDERS["yandex"] = OAuthProvider(
        name="Яндекс",
        client_id=os.getenv("YANDEX_CLIENT_ID", ""),
        client_secret=os.getenv("YANDEX_CLIENT_SECRET", ""),
        authorize_url="https://oauth.yandex.ru/authorize",
        token_url="https://oauth.yandex.ru/token",
        userinfo_url="https://login.yandex.ru/info",
        scope="login:email login:info",
    )

# Sber ID OAuth
if os.getenv("SBER_CLIENT_ID"):
    PROVIDERS["sber"] = OAuthProvider(
        name="Сбер ID",
        client_id=os.getenv("SBER_CLIENT_ID", ""),
        client_secret=os.getenv("SBER_CLIENT_SECRET", ""),
        authorize_url="https://online.sberbank.ru/CSAFront/oidc/authorize",
        token_url="https://online.sberbank.ru/CSAFront/oidc/token",
        userinfo_url="https://online.sberbank.ru/CSAFront/oidc/userinfo",
        scope="openid name email",
    )

# Tinkoff ID OAuth
if os.getenv("TINKOFF_CLIENT_ID"):
    PROVIDERS["tinkoff"] = OAuthProvider(
        name="Тинькофф ID",
        client_id=os.getenv("TINKOFF_CLIENT_ID", ""),
        client_secret=os.getenv("TINKOFF_CLIENT_SECRET", ""),
        authorize_url="https://id.tinkoff.ru/auth/authorize",
        token_url="https://id.tinkoff.ru/auth/token",
        userinfo_url="https://id.tinkoff.ru/userinfo/userinfo",
        scope="openid profile email",
    )


def get_available_providers() -> list[dict]:
    """Возвращает список доступных OAuth провайдеров"""
    return [
        {"id": key, "name": provider.name}
        for key, provider in PROVIDERS.items()
    ]


def get_provider(provider_id: str) -> Optional[OAuthProvider]:
    """Получить провайдера по ID"""
    return PROVIDERS.get(provider_id)


def _build_async_client() -> httpx.AsyncClient:
    """Создаёт HTTP клиент с безопасными таймаутами для внешних OAuth провайдеров."""
    return httpx.AsyncClient(timeout=settings.OAUTH_HTTP_TIMEOUT_SECONDS)


async def exchange_code_for_token(provider: OAuthProvider, code: str, redirect_uri: str) -> dict:
    """Обменять authorization code на access token"""
    async with _build_async_client() as client:
        response = await client.post(
            provider.token_url,
            data={
                "client_id": provider.client_id,
                "client_secret": provider.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        return response.json()


async def get_user_info(provider: OAuthProvider, access_token: str) -> dict:
    """Получить информацию о пользователе от провайдера"""
    async with _build_async_client() as client:
        # Yandex использует другой формат
        if "yandex" in provider.token_url:
            response = await client.get(
                provider.userinfo_url,
                params={"oauth_token": access_token},
                headers={"Accept": "application/json"},
            )
        else:
            response = await client.get(
                provider.userinfo_url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
        response.raise_for_status()
        return response.json()


def normalize_user_info(provider_id: str, raw_info: dict) -> dict:
    """Нормализовать данные пользователя от разных провайдеров"""
    if provider_id == "google":
        return {
            "email": raw_info.get("email"),
            "name": raw_info.get("name"),
            "provider_id": raw_info.get("id"),
        }
    elif provider_id == "yandex":
        return {
            "email": raw_info.get("default_email"),
            "name": raw_info.get("real_name") or raw_info.get("display_name"),
            "provider_id": raw_info.get("id"),
        }
    elif provider_id == "sber":
        return {
            "email": raw_info.get("email"),
            "name": raw_info.get("name"),
            "provider_id": raw_info.get("sub"),
        }
    elif provider_id == "tinkoff":
        return {
            "email": raw_info.get("email"),
            "name": raw_info.get("name"),
            "provider_id": raw_info.get("sub"),
        }
    return {}
