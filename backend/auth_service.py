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
import jwt
from jwt import InvalidTokenError
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

    PR 26: добавлен `jti` (JWT ID) — позволяет отзывать токены через
    `revoked_tokens` таблицу (на logout, при инциденте). Раньше только
    refresh tokens имели jti, access tokens были неотзываемыми.
    """
    to_encode = data.copy()

    if expires_delta:
        expire = utc_now_naive() + expires_delta
    else:
        expire = utc_now_naive() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({
        "exp": expire,
        "iat": utc_now_naive(),  # API-07: маркер для tokens_valid_after-инвалидации
        "type": "access",
        "jti": secrets.token_urlsafe(16),  # PR 26: revocation support
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
        "iat": utc_now_naive(),  # API-07: маркер для tokens_valid_after-инвалидации
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


OAUTH_2FA_PENDING_TOKEN_EXPIRE_MINUTES = 5


def create_2fa_pending_token(user_id: int) -> str:
    """S1-06b: короткоживущий токен для OAuth-2FA challenge-flow.

    Подписан SECRET_KEY (как access token), но `type="2fa_pending"` —
    decode_access_token его отвергает (type mismatch), поэтому он НЕ даёт
    доступа ни к одному защищённому эндпоинту через get_current_user.
    """
    to_encode = {
        "sub": str(user_id),
        "type": "2fa_pending",
        "exp": utc_now_naive() + timedelta(minutes=OAUTH_2FA_PENDING_TOKEN_EXPIRE_MINUTES),
        "iat": utc_now_naive(),
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_2fa_pending_token(token: str) -> Optional[int]:
    """Валидирует pending-2FA токен (подпись, exp, scope). Возвращает user_id."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except InvalidTokenError:
        return None

    if payload.get("type") != "2fa_pending":
        return None

    sub = payload.get("sub")
    if sub is None:
        return None

    return int(sub) if isinstance(sub, str) else sub


def decode_access_token(token: str) -> Optional[schemas.TokenData]:
    """Декодирование Access JWT токена.

    PR 26: возвращает также `jti` и `exp_ts` — нужны для revocation check.
    """
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

        return schemas.TokenData(
            user_id=user_id,
            email=email,
            jti=payload.get("jti"),
            exp_ts=payload.get("exp"),
            iat_ts=payload.get("iat"),
        )
    except InvalidTokenError:
        return None


def decode_refresh_token(token: str) -> Optional[schemas.TokenData]:
    """
    Декодирование Refresh JWT токена.

    PR 26: возвращает также `jti` и `exp_ts` — для revocation.

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

        return schemas.TokenData(
            user_id=user_id,
            email=email,
            jti=payload.get("jti"),
            exp_ts=payload.get("exp"),
            iat_ts=payload.get("iat"),
        )
    except InvalidTokenError:
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

    # API-07: refresh-токен, выпущенный до reset/change-password, инвалидирован.
    if is_token_stale(user, token_data.iat_ts):
        return None

    # API-05 reuse-detection: уже ротированный (отозванный) refresh — replay-атака.
    if is_token_revoked(db, token_data.jti):
        return None

    # API-05 строгая ротация: отзываем предъявленный refresh ДО выпуска новой пары.
    revoke_token(
        db,
        jti=token_data.jti,
        user_id=token_data.user_id,
        exp_ts=token_data.exp_ts,
        reason="rotated",
    )

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

    # Создаём дефолтный аккаунт для пользователя — только если ещё нет.
    # Idempotent: повторный вызов register не создаст дубликат
    # (страховка на случай race condition при медленном frontend retry).
    existing = db.query(models.Account).filter(
        models.Account.user_id == db_user.id
    ).first()
    if existing is None:
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

    # API-11 account-lockout: заблокированный аккаунт отвергаем даже с верным
    # паролем (generic 401 — lock-state клиенту не раскрываем).
    if user.locked_until and user.locked_until > utc_now_naive():
        return None

    if not verify_password(password, user.hashed_password):
        # API-11: счётчик неудач; при достижении порога — лок на N минут.
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.LOGIN_MAX_FAILED_ATTEMPTS:
            user.locked_until = utc_now_naive() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            user.failed_login_count = 0
        db.commit()
        return None

    # API-11: успешный вход сбрасывает счётчик и снимает блокировку.
    user.failed_login_count = 0
    user.locked_until = None

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
        # Phase 11 (2026-05-17): валидация settings keys/values через whitelist
        # — защита от storage abuse и поломки фронта invalid значениями.
        from services.user_settings import validate_settings
        # Merge into existing settings (partial update pattern)
        existing = user.settings if isinstance(user.settings, dict) else {}
        sanitized_new = validate_settings(user_data.settings)
        user.settings = {**existing, **sanitized_new}

    db.commit()
    db.refresh(user)
    return user


# ==================== JWT REVOCATION (PR 26) ====================

def is_token_revoked(db: Session, jti: Optional[str]) -> bool:
    """PR 26: проверка что JWT jti не в revoked_tokens.

    Раньше JWT никогда не отзывались — украденный токен оставался валидным
    до естественного expiry. Теперь logout записывает jti в revoked_tokens
    и каждый get_current_user проверяет, что jti отсутствует.
    """
    if not jti:
        return False
    return db.query(models.RevokedTokenORM).filter(
        models.RevokedTokenORM.jti == jti
    ).first() is not None


def is_token_stale(user: models.User, iat_ts: Optional[int]) -> bool:
    """API-07: токен устарел, если выпущен ДО/в ту же секунду что reset/change-password.

    `user.tokens_valid_after` ставится в момент сброса/смены пароля. Любой токен с
    `iat <= tokens_valid_after` инвалидируется (секундное разрешение + 1s leeway на
    маркере — токен, выпущенный в ту же секунду, не должен пережить сброс).
    Пользователь без маркера (NULL) → ничего не инвалидируется.
    """
    if user.tokens_valid_after is None or iat_ts is None:
        return False
    from datetime import timezone as _tz
    token_issued_at = datetime.fromtimestamp(iat_ts, tz=_tz.utc).replace(tzinfo=None)
    return token_issued_at < user.tokens_valid_after + timedelta(seconds=1)


def revoke_token(
    db: Session,
    *,
    jti: Optional[str],
    user_id: int,
    exp_ts: Optional[int],
    reason: str = "logout",
) -> None:
    """PR 26: записать jti в revoked_tokens (best-effort, не падает).

    Используется в /auth/logout, /admin/users/{id}/revoke-sessions.
    """
    if not jti:
        return
    try:
        from datetime import datetime as _dt, timezone as _tz

        expires_at = (
            _dt.fromtimestamp(exp_ts, tz=_tz.utc).replace(tzinfo=None)
            if exp_ts
            else utc_now_naive() + timedelta(days=7)
        )
        existing = db.query(models.RevokedTokenORM).filter(
            models.RevokedTokenORM.jti == jti
        ).first()
        if existing:
            return  # idempotent
        db.add(models.RevokedTokenORM(
            jti=jti,
            user_id=user_id,
            revoked_at=utc_now_naive(),
            expires_at=expires_at,
            reason=reason,
        ))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


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

    # PR 26: проверка revocation. Украденный/отозванный токен → 401.
    if is_token_revoked(db, token_data.jti):
        raise credentials_exception

    user = get_user_by_id(db, token_data.user_id)

    if user is None:
        raise credentials_exception

    # API-07: токен, выпущенный до reset/change-password, инвалидирован.
    if is_token_stale(user, token_data.iat_ts):
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

