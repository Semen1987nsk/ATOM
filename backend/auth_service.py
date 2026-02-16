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
import secrets

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
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

# Bearer токен для авторизации
security = HTTPBearer(auto_error=False)


# ==================== ПАРОЛИ ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Проверка пароля против хеша"""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def get_password_hash(password: str) -> str:
    """Хеширование пароля"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


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
    
    if credentials is None:
        raise credentials_exception
    
    token = credentials.credentials
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[models.User]:
    """
    Опциональная версия - не выбрасывает ошибку если токена нет.
    Полезно для эндпоинтов, которые работают и с авторизацией и без.
    """
    if credentials is None:
        return None
    
    try:
        token = credentials.credentials
        token_data = decode_access_token(token)
        
        if token_data is None:
            return None
        
        user = get_user_by_id(db, token_data.user_id)
        return user
        
    except Exception:
        return None


def get_user_account(db: Session, user: models.User) -> models.Account:
    """
    Получить основной аккаунт пользователя.
    Если нет - создаёт автоматически.
    """
    account = db.query(models.Account).filter(
        models.Account.user_id == user.id
    ).first()
    
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

