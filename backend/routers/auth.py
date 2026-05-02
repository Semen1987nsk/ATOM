"""
Auth Router — регистрация, вход, профиль, OAuth
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from datetime import datetime
import secrets
import httpx

import database
import models
import schemas
import auth_service
import oauth_service
from oauth_state_store import get_state_store
from rate_limiter import limiter, AUTH_LIMIT, REGISTER_LIMIT
from logger import get_logger

log = get_logger("auth")

router = APIRouter(prefix="/auth", tags=["auth"])

# Хранилище state для OAuth с поддержкой Redis
oauth_store = get_state_store()


# ==================== AUTH ENDPOINTS ====================

@router.post("/register", response_model=schemas.TokenPair)
@limiter.limit(REGISTER_LIMIT)
def register(request: Request, response: Response, user_data: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Регистрация нового пользователя.
    Возвращает пару JWT токенов (access + refresh) для авторизации.
    Rate limit: 3 запроса в минуту.
    """
    existing_user = auth_service.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email уже зарегистрирован"
        )
    
    user = auth_service.create_user(db, user_data)
    
    # Создаём пару токенов
    access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)
    
    log.info(f"✅ Зарегистрирован новый пользователь: {user.email}")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/login", response_model=schemas.TokenPair)
@limiter.limit(AUTH_LIMIT)
def login(request: Request, response: Response, user_data: schemas.UserLogin, db: Session = Depends(database.get_db)):
    """
    Вход в систему.
    Возвращает пару JWT токенов (access + refresh) для авторизации.
    Rate limit: 5 запросов в минуту (защита от brute-force).
    """
    user = auth_service.authenticate_user(db, user_data.email, user_data.password)
    
    if not user:
        raise HTTPException(
            status_code=401,
            detail="Неверный email или пароль"
        )
    
    if user.is_active != 1:
        raise HTTPException(
            status_code=403,
            detail="Аккаунт деактивирован"
        )
    
    # Создаём пару токенов
    access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)
    
    log.info(f"🔑 Вход пользователя: {user.email}")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/refresh", response_model=schemas.TokenPair)
@limiter.limit(AUTH_LIMIT)
def refresh_tokens(
    request: Request,
    response: Response,
    token_request: schemas.TokenRefreshRequest | None = None,
    db: Session = Depends(database.get_db)
):
    """
    Обновление токенов по refresh токену.
    
    Используйте этот endpoint когда access токен истёк.
    Refresh токен должен быть валиден.
    """
    refresh_token = auth_service.get_refresh_token_from_request(
        request,
        token_request.refresh_token if token_request else None,
    )

    if not refresh_token:
        raise HTTPException(
            status_code=401,
            detail="Refresh токен отсутствует"
        )

    result = auth_service.refresh_tokens(refresh_token, db)
    
    if result is None:
        raise HTTPException(
            status_code=401,
            detail="Refresh токен недействителен или истёк"
        )
    
    access_token, refresh_token = result
    auth_service.set_auth_cookies(response, request, access_token, refresh_token)
    
    log.debug("🔄 Токены обновлены")
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response):
    """Завершить сессию и очистить auth cookies."""
    auth_service.clear_auth_cookies(response, request)
    response.status_code = 204
    return response


@router.get("/me", response_model=schemas.UserResponse)
def get_current_user_info(
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Получить информацию о текущем авторизованном пользователе.
    Требует Bearer токен в заголовке Authorization.
    """
    return current_user


@router.get("/subscription")
def get_current_user_subscription(
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Получить информацию о подписке текущего пользователя.
    """
    return auth_service.get_user_subscription(db, current_user)


@router.put("/me", response_model=schemas.UserResponse)
def update_current_user(
    user_data: schemas.UserUpdate,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Обновить профиль текущего пользователя.
    """
    updated_user = auth_service.update_user(db, current_user, user_data)
    log.info(f"✏️ Обновлён профиль пользователя: {updated_user.email}")
    return updated_user


@router.post("/change-password")
def change_password(
    password_data: schemas.ChangePasswordRequest,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Изменить пароль текущего пользователя.
    """
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail="Для OAuth-аккаунта смена пароля недоступна"
        )

    if not auth_service.verify_password(password_data.old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Неверный текущий пароль"
        )
    
    if password_data.old_password == password_data.new_password:
        raise HTTPException(
            status_code=400,
            detail="Новый пароль должен отличаться от текущего"
        )

    if len(password_data.new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Новый пароль должен быть минимум 6 символов"
        )
    
    current_user.hashed_password = auth_service.get_password_hash(password_data.new_password)
    db.commit()
    
    log.info(f"🔒 Пароль изменён для пользователя: {current_user.email}")
    
    return {"message": "Пароль успешно изменён"}


# ==================== OAuth ENDPOINTS ====================

@router.get("/oauth/providers")
def get_oauth_providers():
    """
    Получить список доступных OAuth провайдеров.
    """
    return oauth_service.get_available_providers()


@router.get("/oauth/{provider}/authorize")
@limiter.limit(AUTH_LIMIT)
def oauth_authorize(request: Request, provider: str, redirect_uri: str):
    """
    Получить URL для авторизации через OAuth провайдера.
    Rate limit: 5 запросов в минуту.
    """
    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Провайдер {provider} не поддерживается или не настроен")
    
    state = secrets.token_urlsafe(32)
    oauth_store.set(state, provider)
    
    auth_url = oauth_provider.get_authorize_url(redirect_uri, state)
    return {"authorize_url": auth_url, "state": state}


@router.post("/oauth/{provider}/callback")
@limiter.limit(AUTH_LIMIT)
async def oauth_callback(
    request: Request,
    response: Response,
    provider: str,
    code: str,
    state: str,
    redirect_uri: str,
    db: Session = Depends(database.get_db)
):
    """
    Обработать callback от OAuth провайдера и создать/авторизовать пользователя.
    """
    if not oauth_store.validate_and_delete(state, provider):
        raise HTTPException(status_code=400, detail="Неверный state параметр")
    
    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Провайдер {provider} не поддерживается")
    
    try:
        token_data = await oauth_service.exchange_code_for_token(
            oauth_provider, code, redirect_uri
        )
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=400, detail="Не удалось получить access_token")
        
        raw_user_info = await oauth_service.get_user_info(oauth_provider, access_token)
        user_info = oauth_service.normalize_user_info(provider, raw_user_info)
        
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email не получен от провайдера")
        
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if user:
            if user.oauth_provider != provider:
                user.oauth_provider = provider
                user.oauth_provider_id = user_info.get("provider_id")
            user.last_login = datetime.now()
            db.commit()
        else:
            user = models.User(
                email=email,
                name=user_info.get("name"),
                hashed_password=None,
                oauth_provider=provider,
                oauth_provider_id=user_info.get("provider_id"),
                registration_source=provider,
                last_login=datetime.now(),
                is_active=1,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            default_account = models.Account(
                user_id=user.id,
                name="Основной",
                balance=0,
                currency="RUB"
            )
            db.add(default_account)
            db.commit()
            
            log.info(f"👤 Создан OAuth пользователь: {email} через {provider}")
        
        # Создаём пару токенов
        access_token, refresh_token = auth_service.create_token_pair(user.id, user.email)
        auth_service.set_auth_cookies(response, request, access_token, refresh_token)
        
        log.info(f"🔐 OAuth вход: {email} через {provider}")
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": auth_service.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "oauth_provider": user.oauth_provider,
            }
        }
        
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        log.warning(f"⏱️ OAuth timeout for {provider}: {exc}")
        raise HTTPException(status_code=504, detail="OAuth провайдер не ответил вовремя")
    except httpx.HTTPStatusError as exc:
        log.warning(f"❌ OAuth provider HTTP error for {provider}: {exc}")
        raise HTTPException(status_code=502, detail="Ошибка ответа OAuth провайдера")
    except httpx.HTTPError as exc:
        log.warning(f"❌ OAuth transport error for {provider}: {exc}")
        raise HTTPException(status_code=502, detail="Ошибка соединения с OAuth провайдером")
    except Exception as exc:
        log.error(f"❌ OAuth ошибка для {provider}: {exc}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка OAuth авторизации")
