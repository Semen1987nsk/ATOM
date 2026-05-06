"""
Сервис аутентификации с JWT токенами и хешированием паролей.

Поддерживает:
- Access токены (короткоживущие, 15-60 минут)
- Refresh токены (долгоживущие, 7-30 дней)
- Автоматическое обновление токенов
"""
from datetime import datetime, timedelta
from utils import utc_now_naive
from typing import Optional, Tuple
from hmac import compare_digest
import secrets

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, Response, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from config import settings

# ==================== КОНФИГУРАЦИЯ ====================
# Все секреты берём из единственного источника — config.settings

SECRET_KEY = settings.SECRET_KEY
REFRESH_SECRET_KEY = settings.REFRESH_SECRET_KEY
ALGORITHM = settings.ALGORITHM
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
REFRESH_TOKEN_EXPIRE_DAYS = settings.REFRESH_TOKEN_EXPIRE_DAYS
ACCESS_TOKEN_COOKIE_NAME = settings.ACCESS_TOKEN_COOKIE_NAME
REFRESH_TOKEN_COOKIE_NAME = settings.REFRESH_TOKEN_COOKIE_NAME
CSRF_COOKIE_NAME = settings.CSRF_COOKIE_NAME
CSRF_HEADER_NAME = settings.CSRF_HEADER_NAME

# Bearer токен для авторизации
security = HTTPBearer(auto_error=False)


def _should_use_secure_cookie(request: Request) -> bool:
    """Определяет, должен ли cookie быть secure для текущего запроса."""
    if settings.AUTH_COOKIE_SECURE:
        return True
    return request.url.scheme == "https"


def _base_cookie_params(request: Request) -> dict:
    return {
        "httponly": True,
        "secure": _should_use_secure_cookie(request),
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": settings.AUTH_COOKIE_PATH,
        "domain": settings.AUTH_COOKIE_DOMAIN,
    }


def _csrf_cookie_params(request: Request) -> dict:
    return {
        "httponly": False,
        "secure": _should_use_secure_cookie(request),
        "samesite": settings.AUTH_COOKIE_SAMESITE,
        "path": settings.AUTH_COOKIE_PATH,
        "domain": settings.AUTH_COOKIE_DOMAIN,
    }


def create_csrf_token() -> str:
    """Создать CSRF токен для double-submit cookie защиты."""
    return secrets.token_urlsafe(32)


def set_auth_cookies(response: Response, request: Request, access_token: str, refresh_token: str) -> None:
    """Установить access/refresh cookies с безопасными атрибутами."""
    csrf_token = create_csrf_token()

    response.set_cookie(
        key=ACCESS_TOKEN_COOKIE_NAME,
        value=access_token,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        **_base_cookie_params(request),
    )
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE_NAME,
        value=refresh_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **_base_cookie_params(request),
    )
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60,
        **_csrf_cookie_params(request),
    )


def clear_auth_cookies(response: Response, request: Request) -> None:
    """Очистить auth cookies."""
    cookie_params = {
        "path": settings.AUTH_COOKIE_PATH,
        "domain": settings.AUTH_COOKIE_DOMAIN,
        "secure": _should_use_secure_cookie(request),
        "httponly": True,
        "samesite": settings.AUTH_COOKIE_SAMESITE,
    }
    response.delete_cookie(ACCESS_TOKEN_COOKIE_NAME, **cookie_params)
    response.delete_cookie(REFRESH_TOKEN_COOKIE_NAME, **cookie_params)
    response.delete_cookie(CSRF_COOKIE_NAME, **_csrf_cookie_params(request))


def get_access_token_from_request(request: Request, credentials: Optional[HTTPAuthorizationCredentials]) -> Optional[str]:
    """Извлечь access token из Bearer header или httpOnly cookie."""
    if credentials is not None:
        return credentials.credentials
    return request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)


def get_refresh_token_from_request(request: Request, refresh_token: Optional[str] = None) -> Optional[str]:
    """Извлечь refresh token из body или httpOnly cookie."""
    if refresh_token:
        return refresh_token
    return request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)


def is_cookie_authenticated_request(request: Request) -> bool:
    """Определить, использует ли запрос cookie-based auth вместо Bearer header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.lower().startswith("bearer "):
        return False

    return bool(
        request.cookies.get(ACCESS_TOKEN_COOKIE_NAME)
        or request.cookies.get(REFRESH_TOKEN_COOKIE_NAME)
    )


def validate_csrf_request(request: Request) -> bool:
    """Проверить double-submit CSRF токен для cookie-auth запроса."""
    cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
    header_token = request.headers.get(CSRF_HEADER_NAME)

    if not cookie_token or not header_token:
        return False

    return compare_digest(cookie_token, header_token)


# ==================== ПАРОЛИ ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля против хеша"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """
    Хеширование пароля.

    Используем явный rounds из настроек (по умолчанию 14) — bcrypt.gensalt()
    без аргумента опирается на дефолт библиотеки (12), что недостаточно
    в 2026 году против GPU-bruteforce.
    """
    return bcrypt.hashpw(
        password.encode('utf-8'),
        bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS),
    ).decode('utf-8')


# ==================== JWT ТОКЕНЫ ====================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Создание Access JWT токена.
    
    Access токен используется для аутентификации API запросов.
    Имеет короткий срок жизни для безопасности.
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = utc_now_naive() + expires_delta
    else:
        expire = utc_now_naive() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({
        "exp": expire,
        "type": "access",  # Тип токена для валидации
    })
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Создание Refresh JWT токена.
    
    Refresh токен используется для получения новых access токенов.
    Имеет долгий срок жизни, хранится на клиенте в httpOnly cookie или secure storage.
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = utc_now_naive() + expires_delta
    else:
        expire = utc_now_naive() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    
    # Добавляем уникальный идентификатор для возможности отзыва
    to_encode.update({
        "exp": expire,
        "type": "refresh",
        "jti": secrets.token_urlsafe(16),  # JWT ID для отзыва
    })
    encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_token_pair(user_id: int, email: str) -> Tuple[str, str]:
    """
    Создаёт пару токенов: access + refresh.
    
    Returns:
        Tuple[access_token, refresh_token]
    """
    token_data = {"sub": str(user_id), "email": email}
    
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)
    
    return access_token, refresh_token


def decode_access_token(token: str) -> Optional[schemas.TokenData]:
    """Декодирование Access JWT токена"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        
        # Проверяем тип токена (если указан)
        token_type = payload.get("type")
        if token_type and token_type != "access":
            return None
        
        sub = payload.get("sub")
        email: str = payload.get("email")
        
        if sub is None:
            return None
        
        # sub может быть строкой или int
        user_id = int(sub) if isinstance(sub, str) else sub
            
        return schemas.TokenData(user_id=user_id, email=email)
    except JWTError:
        return None


def decode_refresh_token(token: str) -> Optional[schemas.TokenData]:
    """
    Декодирование Refresh JWT токена.
    
    Returns:
        TokenData если токен валиден, None иначе.
    """
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        
        # Проверяем тип токена
        token_type = payload.get("type")
        if token_type != "refresh":
            return None
        
        sub = payload.get("sub")
        email: str = payload.get("email")
        
        if sub is None:
            return None
        
        user_id = int(sub) if isinstance(sub, str) else sub
            
        return schemas.TokenData(user_id=user_id, email=email)
    except JWTError:
        return None


def refresh_tokens(refresh_token: str, db: Session) -> Optional[Tuple[str, str]]:
    """
    Обновление пары токенов по refresh токену.
    
    Returns:
        Tuple[new_access_token, new_refresh_token] или None если refresh невалиден.
    """
    token_data = decode_refresh_token(refresh_token)
    
    if token_data is None:
        return None
    
    # Проверяем что пользователь существует и активен
    user = get_user_by_id(db, token_data.user_id)
    if user is None or user.is_active != 1:
        return None
    
    # Создаём новую пару токенов
    return create_token_pair(user.id, user.email)


# ==================== РАБОТА С ПОЛЬЗОВАТЕЛЯМИ ====================

def get_user_by_email(db: Session, email: str) -> Optional[models.User]:
    """Получить пользователя по email"""
    return db.query(models.User).filter(models.User.email == email).first()


def get_user_by_id(db: Session, user_id: int) -> Optional[models.User]:
    """Получить пользователя по ID"""
    return db.query(models.User).filter(models.User.id == user_id).first()


def create_user(db: Session, user_data: schemas.UserCreate, utm_data: dict = None) -> models.User:
    """Создать нового пользователя"""
    hashed_password = get_password_hash(user_data.password)
    
    db_user = models.User(
        email=user_data.email,
        name=user_data.name,
        hashed_password=hashed_password,
        is_active=1,
        registration_source="email",
        settings={}
    )
    
    # UTM данные если переданы
    if utm_data:
        db_user.utm_source = utm_data.get("utm_source")
        db_user.utm_medium = utm_data.get("utm_medium")
        db_user.utm_campaign = utm_data.get("utm_campaign")
        db_user.referrer = utm_data.get("referrer")
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Создаём дефолтный аккаунт для пользователя
    default_account = models.Account(
        user_id=db_user.id,
        name="Основной счёт",
        balance=0,
        currency="RUB"
    )
    db.add(default_account)
    db.commit()
    
    return db_user


def authenticate_user(db: Session, email: str, password: str) -> Optional[models.User]:
    """Аутентификация пользователя"""
    user = get_user_by_email(db, email)
    
    if not user:
        # Dummy bcrypt check to prevent timing attacks (email enumeration)
        bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt()))
        return None
    
    # OAuth-only users don't have a password — can't authenticate with password
    if not user.hashed_password:
        return None
    
    if not verify_password(password, user.hashed_password):
        return None
    
    # Обновляем last_login
    try:
        user.last_login = utc_now_naive()
        db.commit()
    except Exception:
        db.rollback()  # Don't fail login if timestamp update fails
    
    return user


def update_user(db: Session, user: models.User, user_data: schemas.UserUpdate) -> models.User:
    """Обновить данные пользователя"""
    if user_data.name is not None:
        user.name = user_data.name
    
    if user_data.settings is not None:
        user.settings = user_data.settings
    
    db.commit()
    db.refresh(user)
    return user


# ==================== DEPENDENCY ДЛЯ ЗАЩИЩЁННЫХ ЭНДПОИНТОВ ====================

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> models.User:
    """
    Dependency для получения текущего авторизованного пользователя.
    Используется в защищённых эндпоинтах.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не удалось проверить учётные данные",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    token = get_access_token_from_request(request, credentials)

    if token is None:
        raise credentials_exception

    token_data = decode_access_token(token)
    
    if token_data is None:
        raise credentials_exception
    
    user = get_user_by_id(db, token_data.user_id)
    
    if user is None:
        raise credentials_exception
    
    if user.is_active != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт деактивирован"
        )
    
    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    """
    Опциональная версия - не выбрасывает ошибку если токена нет.
    Полезно для эндпоинтов, которые работают и с авторизацией и без.
    """
    token = get_access_token_from_request(request, credentials)
    if token is None:
        return None
    
    try:
        token_data = decode_access_token(token)
        
        if token_data is None:
            return None
        
        user = get_user_by_id(db, token_data.user_id)
        return user
        
    except Exception:
        return None


def get_user_account(db: Session, user: models.User) -> models.Account:
    """
    Возвращает АКТИВНЫЙ счёт пользователя.

    Активный счёт — тот, чей id записан в user.settings['active_account_id'].
    Если значение отсутствует или указывает на несуществующий/чужой счёт —
    возвращаем первый по списку. Если счетов нет вообще — создаём дефолтный.
    """
    # 1) Пытаемся прочитать activeAccount из settings
    settings = (user.settings or {}) if isinstance(user.settings, dict) else {}
    active_id = settings.get("active_account_id")

    if active_id:
        account = db.query(models.Account).filter(
            models.Account.id == active_id,
            models.Account.user_id == user.id,
        ).first()
        if account:
            return account

    # 2) Fallback на первый счёт пользователя
    account = db.query(models.Account).filter(
        models.Account.user_id == user.id
    ).order_by(models.Account.id.asc()).first()

    if not account:
        # Создаём дефолтный аккаунт
        account = models.Account(
            user_id=user.id,
            name="Основной счёт",
            balance=0,
            currency="RUB"
        )
        db.add(account)
        db.commit()
        db.refresh(account)

    return account


def get_account_id(db: Session, user: models.User) -> int:
    """
    Convenience wrapper: returns just the account ID.
    Use this in routers to avoid duplicating get_user_account + .id
    """
    return get_user_account(db, user).id


def get_user_subscription(db: Session, user: models.User) -> dict:
    """
    Получить текущую подписку пользователя.
    Если нет активной - возвращает Free план.
    """
    subscription = db.query(models.Subscription).filter(
        models.Subscription.user_id == user.id,
        models.Subscription.is_active == 1
    ).first()
    
    if not subscription:
        # Возвращаем Free план
        return {
            "plan": "free",
            "is_active": True,
            "started_at": user.created_at.isoformat() if user.created_at else None,
            "expires_at": None,
            "auto_renew": False,
            "limits": {
                "max_trades": 50,
                "max_accounts": 1,
                "ai_analysis": False,
            }
        }
    
    return {
        "plan": subscription.plan.value,
        "is_active": bool(subscription.is_active),
        "started_at": subscription.started_at.isoformat() if subscription.started_at else None,
        "expires_at": subscription.expires_at.isoformat() if subscription.expires_at else None,
        "auto_renew": bool(subscription.auto_renew),
        "limits": {
            "max_trades": subscription.max_trades,
            "max_accounts": subscription.max_accounts,
            "ai_analysis": bool(subscription.ai_analysis_enabled),
        }
    }

