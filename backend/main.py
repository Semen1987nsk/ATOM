from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Query
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, RedirectResponse
import database
from sqlalchemy.orm import Session
import models
import schemas
import analytics
import ai_service
import import_service
import market_service
import auth_service
import oauth_service
import csv
import io
import secrets
from logger import get_logger
from datetime import datetime, timedelta
from typing import Optional

log = get_logger("api")

# Инициализируем сервисы
market_data_service = market_service.MarketService()

# Инициализируем базу данных при запуске
database.init_db()

app = FastAPI(
    title="ATOM API",
    description="API для умного торгового дневника ATOM (ранее UniFlow).",
    version="0.1.0",
    docs_url=None, # Отключаем стандартный роут
    redoc_url=None,
)

# Настройка CORS (разрешаем запросы с любых доменов, важно для Codespaces)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_origin_regex=r"https://.*\.app\.github\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ручная настройка Swagger UI для работы через HTTPS прокси
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js",
        swagger_css_url="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css",
    )

@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="https://unpkg.com/redoc@next/bundles/redoc.standalone.js",
    )

@app.on_event("startup")
async def startup_event():
    log.info("🚀 ATOM API Starting...")
    log.debug("Registered routes:")
    for route in app.routes:
        log.debug(f"  → {route.path} ({route.name})")

@app.get("/test-docs", include_in_schema=False)
async def custom_docs():
    return {"message": "Test route works. If you see this, the server is fine."}

@app.get("/")
async def read_root():
    return {"message": "Добро пожаловать в API для ATOM!"}


# ==================== AUTH ENDPOINTS ====================

@app.post("/auth/register", response_model=schemas.Token, tags=["auth"])
def register(user_data: schemas.UserCreate, db: Session = Depends(database.get_db)):
    """
    Регистрация нового пользователя.
    Возвращает JWT токен для авторизации.
    """
    # Проверяем, не занят ли email
    existing_user = auth_service.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email уже зарегистрирован"
        )
    
    # Создаём пользователя
    user = auth_service.create_user(db, user_data)
    
    # Создаём токен (sub должен быть строкой для JWT)
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    log.info(f"✅ Зарегистрирован новый пользователь: {user.email}")
    
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/auth/login", response_model=schemas.Token, tags=["auth"])
def login(user_data: schemas.UserLogin, db: Session = Depends(database.get_db)):
    """
    Вход в систему.
    Возвращает JWT токен для авторизации.
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
    
    access_token = auth_service.create_access_token(
        data={"sub": str(user.id), "email": user.email}
    )
    
    log.info(f"🔑 Вход пользователя: {user.email}")
    
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/auth/me", response_model=schemas.UserResponse, tags=["auth"])
def get_current_user_info(
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Получить информацию о текущем авторизованном пользователе.
    Требует Bearer токен в заголовке Authorization.
    """
    return current_user


@app.get("/auth/subscription", tags=["auth"])
def get_current_user_subscription(
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Получить информацию о подписке текущего пользователя.
    """
    return auth_service.get_user_subscription(db, current_user)


@app.put("/auth/me", response_model=schemas.UserResponse, tags=["auth"])
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


@app.post("/auth/change-password", tags=["auth"])
def change_password(
    old_password: str,
    new_password: str,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db)
):
    """
    Изменить пароль текущего пользователя.
    """
    # Проверяем старый пароль
    if not auth_service.verify_password(old_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400,
            detail="Неверный текущий пароль"
        )
    
    if len(new_password) < 6:
        raise HTTPException(
            status_code=400,
            detail="Новый пароль должен быть минимум 6 символов"
        )
    
    # Обновляем пароль
    current_user.hashed_password = auth_service.get_password_hash(new_password)
    db.commit()
    
    log.info(f"🔒 Пароль изменён для пользователя: {current_user.email}")
    
    return {"message": "Пароль успешно изменён"}


# ==================== OAuth ENDPOINTS ====================

# Хранилище state для проверки (в продакшене использовать Redis)
oauth_states: dict[str, str] = {}

@app.get("/auth/oauth/providers", tags=["oauth"])
def get_oauth_providers():
    """
    Получить список доступных OAuth провайдеров.
    """
    return oauth_service.get_available_providers()


@app.get("/auth/oauth/{provider}/authorize", tags=["oauth"])
def oauth_authorize(provider: str, redirect_uri: str):
    """
    Получить URL для авторизации через OAuth провайдера.
    """
    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Провайдер {provider} не поддерживается или не настроен")
    
    # Генерируем state для защиты от CSRF
    state = secrets.token_urlsafe(32)
    oauth_states[state] = provider
    
    auth_url = oauth_provider.get_authorize_url(redirect_uri, state)
    return {"authorize_url": auth_url, "state": state}


@app.post("/auth/oauth/{provider}/callback", tags=["oauth"])
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    redirect_uri: str,
    db: Session = Depends(database.get_db)
):
    """
    Обработать callback от OAuth провайдера и создать/авторизовать пользователя.
    """
    # Проверяем state
    if state not in oauth_states or oauth_states[state] != provider:
        raise HTTPException(status_code=400, detail="Неверный state параметр")
    
    del oauth_states[state]  # Удаляем использованный state
    
    oauth_provider = oauth_service.get_provider(provider)
    if not oauth_provider:
        raise HTTPException(status_code=400, detail=f"Провайдер {provider} не поддерживается")
    
    try:
        # Обмениваем code на access_token
        token_data = await oauth_service.exchange_code_for_token(
            oauth_provider, code, redirect_uri
        )
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise HTTPException(status_code=400, detail="Не удалось получить access_token")
        
        # Получаем информацию о пользователе
        raw_user_info = await oauth_service.get_user_info(oauth_provider, access_token)
        user_info = oauth_service.normalize_user_info(provider, raw_user_info)
        
        email = user_info.get("email")
        if not email:
            raise HTTPException(status_code=400, detail="Email не получен от провайдера")
        
        # Ищем существующего пользователя
        user = db.query(models.User).filter(models.User.email == email).first()
        
        if user:
            # Обновляем OAuth данные если изменился провайдер
            if user.oauth_provider != provider:
                user.oauth_provider = provider
                user.oauth_provider_id = user_info.get("provider_id")
            # Обновляем last_login
            user.last_login = datetime.now()
            db.commit()
        else:
            # Создаём нового пользователя
            user = models.User(
                email=email,
                name=user_info.get("name"),
                hashed_password=None,  # OAuth пользователи без пароля
                oauth_provider=provider,
                oauth_provider_id=user_info.get("provider_id"),
                registration_source=provider,  # Источник регистрации
                last_login=datetime.now(),
                is_active=1,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            
            # Создаём дефолтный аккаунт
            default_account = models.Account(
                user_id=user.id,
                name="Основной",
                balance=0,
                currency="RUB"
            )
            db.add(default_account)
            db.commit()
            
            log.info(f"👤 Создан OAuth пользователь: {email} через {provider}")
        
        # Генерируем JWT токен
        jwt_token = auth_service.create_access_token(data={"sub": user.email})
        
        log.info(f"🔐 OAuth вход: {email} через {provider}")
        
        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "oauth_provider": user.oauth_provider,
            }
        }
        
    except Exception as e:
        log.error(f"❌ OAuth ошибка для {provider}: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Ошибка авторизации: {str(e)}")


# ==================== ADMIN ENDPOINTS ====================

import admin_service

def require_admin(current_user: models.User = Depends(auth_service.get_current_user)):
    """Dependency для проверки прав администратора"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Требуются права администратора"
        )
    return current_user


@app.get("/admin/stats", tags=["admin"])
def admin_get_stats(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Основные метрики для дашборда администратора"""
    return admin_service.get_overview_stats(db)


@app.get("/admin/users", tags=["admin"])
def admin_get_users(
    skip: int = 0,
    limit: int = 50,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    search: Optional[str] = None,
    registration_source: Optional[str] = None,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Список пользователей с фильтрацией и пагинацией"""
    return admin_service.get_users_list(
        db, skip, limit, sort_by, sort_order, search, registration_source
    )


@app.get("/admin/registration-sources", tags=["admin"])
def admin_get_registration_sources(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Распределение пользователей по источникам регистрации"""
    return admin_service.get_registration_sources(db)


@app.get("/admin/utm-analytics", tags=["admin"])
def admin_get_utm_analytics(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Аналитика UTM меток"""
    return admin_service.get_utm_analytics(db)


@app.get("/admin/growth", tags=["admin"])
def admin_get_growth(
    days: int = 30,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """График роста пользователей"""
    return admin_service.get_user_growth(db, days)


@app.get("/admin/cohorts", tags=["admin"])
def admin_get_cohorts(
    weeks: int = 8,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Когортный анализ retention"""
    return admin_service.get_cohort_retention(db, weeks)


@app.get("/admin/power-users", tags=["admin"])
def admin_get_power_users(
    limit: int = 20,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Топ активных пользователей"""
    return admin_service.get_power_users(db, limit)


@app.get("/admin/inactive-users", tags=["admin"])
def admin_get_inactive_users(
    days: int = 30,
    limit: int = 50,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Неактивные пользователи (churn risk)"""
    return admin_service.get_inactive_users(db, days, limit)


@app.get("/admin/funnel", tags=["admin"])
def admin_get_funnel(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Воронка конверсии"""
    return admin_service.get_conversion_funnel(db)


@app.post("/admin/users/{user_id}/toggle-admin", tags=["admin"])
def admin_toggle_admin(
    user_id: int,
    is_admin: bool,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Установить/снять права администратора"""
    try:
        user = admin_service.set_user_admin(db, user_id, is_admin)
        return {"message": f"Права администратора {'выданы' if is_admin else 'отозваны'}", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/admin/users/{user_id}/toggle-active", tags=["admin"])
def admin_toggle_active(
    user_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Активировать/деактивировать пользователя"""
    try:
        user = admin_service.toggle_user_active(db, user_id)
        return {"message": f"Пользователь {'активирован' if user.is_active else 'деактивирован'}", "user_id": user.id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/admin/revenue", tags=["admin"])
def admin_get_revenue(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Метрики по выручке и платным подпискам"""
    return admin_service.get_revenue_stats(db)


@app.get("/admin/revenue-growth", tags=["admin"])
def admin_get_revenue_growth(
    days: int = 30,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """График выручки по дням"""
    return admin_service.get_revenue_growth(db, days)


@app.get("/admin/subscription-analytics", tags=["admin"])
def admin_get_subscription_analytics(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Аналитика по подпискам"""
    return admin_service.get_subscription_analytics(db)


@app.get("/admin/top-paying-users", tags=["admin"])
def admin_get_top_paying_users(
    limit: int = 10,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Топ платящих пользователей"""
    return admin_service.get_top_paying_users(db, limit)


# ==================== BLOG ENDPOINTS ====================

import blog_service

@app.get("/blog/articles", tags=["blog"])
def get_articles(
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    featured: bool = False,
    db: Session = Depends(database.get_db)
):
    """Получение списка опубликованных статей"""
    articles = blog_service.get_articles(
        db, skip=skip, limit=limit, category=category,
        tag=tag, published_only=True, featured_only=featured, search=search
    )
    return [blog_service.article_to_list_item(a, db) for a in articles]


@app.get("/blog/articles/count", tags=["blog"])
def get_articles_count(
    category: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """Количество статей"""
    return {"count": blog_service.get_articles_count(db, category=category)}


@app.get("/blog/categories", tags=["blog"])
def get_blog_categories(db: Session = Depends(database.get_db)):
    """Категории блога со статистикой"""
    stats = blog_service.get_category_stats(db)
    categories = [
        {"id": "news", "name": "Новости", "count": stats.get("news", 0)},
        {"id": "guides", "name": "Гайды", "count": stats.get("guides", 0)},
        {"id": "analytics", "name": "Аналитика", "count": stats.get("analytics", 0)},
        {"id": "tips", "name": "Советы", "count": stats.get("tips", 0)},
        {"id": "updates", "name": "Обновления", "count": stats.get("updates", 0)},
    ]
    return categories


@app.get("/blog/tags", tags=["blog"])
def get_blog_tags(db: Session = Depends(database.get_db)):
    """Все теги блога"""
    return blog_service.get_all_tags(db)


@app.get("/blog/popular", tags=["blog"])
def get_popular_articles(
    limit: int = 5,
    db: Session = Depends(database.get_db)
):
    """Популярные статьи"""
    articles = blog_service.get_popular_articles(db, limit)
    return [blog_service.article_to_list_item(a, db) for a in articles]


@app.get("/blog/article/{slug}", tags=["blog"])
def get_article_by_slug(
    slug: str,
    db: Session = Depends(database.get_db)
):
    """Получение статьи по slug"""
    article = blog_service.get_article_by_slug(db, slug, increment_views=True)
    if not article or not article.is_published:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    
    response = blog_service.article_to_response(article, db)
    
    # Добавляем похожие статьи
    related = blog_service.get_related_articles(db, article, limit=3)
    response["related_articles"] = [blog_service.article_to_list_item(a, db) for a in related]
    
    return response


# ==================== ADMIN BLOG ENDPOINTS ====================

@app.get("/admin/articles", tags=["admin", "blog"])
def admin_get_all_articles(
    skip: int = 0,
    limit: int = 50,
    category: Optional[str] = None,
    published: Optional[bool] = None,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Получение всех статей (включая черновики) для админа"""
    query = db.query(models.Article)
    
    if category:
        try:
            cat = models.ArticleCategory(category)
            query = query.filter(models.Article.category == cat)
        except ValueError:
            pass
    
    if published is not None:
        query = query.filter(models.Article.is_published == (1 if published else 0))
    
    articles = query.order_by(models.Article.created_at.desc()).offset(skip).limit(limit).all()
    return [blog_service.article_to_response(a, db) for a in articles]


@app.get("/admin/articles/{article_id}", tags=["admin", "blog"])
def admin_get_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Получение статьи по ID для редактирования"""
    article = blog_service.get_article_by_id(db, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return blog_service.article_to_response(article, db)


@app.post("/admin/articles", tags=["admin", "blog"])
def admin_create_article(
    article_data: schemas.ArticleCreate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Создание новой статьи"""
    article = blog_service.create_article(db, article_data, admin.id)
    return blog_service.article_to_response(article, db)


@app.put("/admin/articles/{article_id}", tags=["admin", "blog"])
def admin_update_article(
    article_id: int,
    article_data: schemas.ArticleUpdate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Обновление статьи"""
    article = blog_service.update_article(db, article_id, article_data)
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return blog_service.article_to_response(article, db)


@app.delete("/admin/articles/{article_id}", tags=["admin", "blog"])
def admin_delete_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Удаление статьи"""
    success = blog_service.delete_article(db, article_id)
    if not success:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {"message": "Статья удалена"}


@app.post("/admin/articles/{article_id}/publish", tags=["admin", "blog"])
def admin_publish_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Публикация статьи"""
    article = blog_service.update_article(db, article_id, schemas.ArticleUpdate(is_published=True))
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {"message": "Статья опубликована", "published_at": article.published_at}


@app.post("/admin/articles/{article_id}/unpublish", tags=["admin", "blog"])
def admin_unpublish_article(
    article_id: int,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Снятие статьи с публикации"""
    article = blog_service.update_article(db, article_id, schemas.ArticleUpdate(is_published=False))
    if not article:
        raise HTTPException(status_code=404, detail="Статья не найдена")
    return {"message": "Статья снята с публикации"}


# ==================== HELPER: Get user's account ====================

def get_account_id(db: Session, user: Optional[models.User] = None) -> int:
    """Получить account_id для текущего пользователя или вернуть 1 для анонима"""
    if user:
        account = auth_service.get_user_account(db, user)
        return account.id
    return 1  # Fallback для обратной совместимости


# ==================== TRADE ENDPOINTS ====================

@app.post("/trades/", response_model=schemas.Trade)
async def create_trade(
    trade: schemas.TradeCreate, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    
    # 1. Check for existing open trades for this symbol (только для этого аккаунта)
    open_trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.symbol == trade.symbol,
        models.Trade.exit_at == None
    ).order_by(models.Trade.entry_at).all()

    # 2. Determine if this is a closing operation
    is_closing = False
    if open_trades:
        # Check direction of the first open trade
        if open_trades[0].direction != trade.direction:
            is_closing = True

    if is_closing:
        qty_to_close = float(trade.quantity)
        last_modified_trade = None
        
        # We iterate through open trades (FIFO)
        for open_trade in open_trades:
            if qty_to_close <= 0:
                break
            
            available_qty = float(open_trade.quantity)
            
            if qty_to_close >= available_qty:
                # Full close of this open trade
                open_trade.exit_price = trade.entry_price
                open_trade.exit_at = trade.entry_at
                open_trade.exit_reason = trade.setup_name or "Manual Close"
                
                # Рассчитываем MAE/MFE из исторических данных MOEX
                try:
                    mae, mfe = market_data_service.calculate_mae_mfe(
                        ticker=open_trade.symbol,
                        direction=open_trade.direction.value,
                        entry_price=float(open_trade.entry_price),
                        entry_time=open_trade.entry_at,
                        exit_time=trade.entry_at
                    )
                    if mae is not None:
                        open_trade.mae_price = mae
                    if mfe is not None:
                        open_trade.mfe_price = mfe
                except Exception as e:
                    log.warning(f"Failed to calculate MAE/MFE for trade {open_trade.id}: {e}")
                
                # Calculate PnL
                if open_trade.direction == models.TradeDirection.LONG:
                    open_trade.pnl = (float(open_trade.exit_price) - float(open_trade.entry_price)) * float(open_trade.quantity)
                else:
                    open_trade.pnl = (float(open_trade.entry_price) - float(open_trade.exit_price)) * float(open_trade.quantity)
                
                # Commission handling
                ratio = available_qty / float(trade.quantity)
                exit_comm = (trade.commission or 0) * ratio
                open_trade.exit_commission = exit_comm
                open_trade.commission = float(open_trade.commission or 0) + exit_comm
                open_trade.net_pnl = open_trade.pnl - open_trade.commission - float(open_trade.swap or 0)

                qty_to_close -= available_qty
                last_modified_trade = open_trade
                
            else:
                # Partial close - Split the trade
                # Create new "Closed" trade
                closed_trade = models.Trade(
                    account_id=open_trade.account_id,
                    symbol=open_trade.symbol,
                    asset_name=open_trade.asset_name,
                    asset_type=open_trade.asset_type,
                    direction=open_trade.direction,
                    entry_price=open_trade.entry_price,
                    quantity=qty_to_close,
                    entry_at=open_trade.entry_at,
                    setup_name=open_trade.setup_name,
                    notes=open_trade.notes,
                    tags=open_trade.tags
                )
                
                # Split Entry Commission
                ratio = qty_to_close / available_qty
                part_entry_comm = float(open_trade.entry_commission or 0) * ratio
                closed_trade.entry_commission = part_entry_comm
                
                # Update original trade's entry commission
                open_trade.entry_commission = float(open_trade.entry_commission or 0) - part_entry_comm
                open_trade.commission = float(open_trade.commission or 0) - part_entry_comm
                
                # Exit details for closed trade
                closed_trade.exit_price = trade.entry_price
                closed_trade.exit_at = trade.entry_at
                closed_trade.exit_reason = trade.setup_name or "Manual Partial Close"
                
                # Exit Commission
                total_close_qty = float(trade.quantity)
                exit_comm_ratio = qty_to_close / total_close_qty
                exit_comm = (trade.commission or 0) * exit_comm_ratio
                
                closed_trade.exit_commission = exit_comm
                closed_trade.commission = closed_trade.entry_commission + exit_comm
                
                # Calculate PnL
                if closed_trade.direction == models.TradeDirection.LONG:
                    closed_trade.pnl = (float(closed_trade.exit_price) - float(closed_trade.entry_price)) * float(closed_trade.quantity)
                else:
                    closed_trade.pnl = (float(closed_trade.entry_price) - float(closed_trade.exit_price)) * float(closed_trade.quantity)
                
                closed_trade.net_pnl = closed_trade.pnl - closed_trade.commission
                
                # Рассчитываем MAE/MFE для closed_trade
                try:
                    mae, mfe = market_data_service.calculate_mae_mfe(
                        ticker=closed_trade.symbol,
                        direction=closed_trade.direction.value,
                        entry_price=float(closed_trade.entry_price),
                        entry_time=closed_trade.entry_at,
                        exit_time=trade.entry_at
                    )
                    if mae is not None:
                        closed_trade.mae_price = mae
                    if mfe is not None:
                        closed_trade.mfe_price = mfe
                except Exception as e:
                    log.warning(f"Failed to calculate MAE/MFE for partial close: {e}")
                
                db.add(closed_trade)
                
                # Update original trade
                open_trade.quantity = float(open_trade.quantity) - qty_to_close
                
                qty_to_close = 0
                last_modified_trade = closed_trade
        
        # If quantity remains, create a new trade (Flip)
        if qty_to_close > 0:
            remainder_trade_data = trade.model_dump()
            remainder_trade = models.Trade(**remainder_trade_data)
            remainder_trade.quantity = qty_to_close
            
            total_qty = float(trade.quantity)
            rem_ratio = qty_to_close / total_qty
            remainder_trade.commission = (trade.commission or 0) * rem_ratio
            remainder_trade.entry_commission = remainder_trade.commission
            
            db.add(remainder_trade)
            last_modified_trade = remainder_trade
            
        db.commit()
        if last_modified_trade:
            db.refresh(last_modified_trade)
            return last_modified_trade
        return open_trades[0]

    else:
        # Standard New Trade
        db_trade = models.Trade(**trade.model_dump())
        db_trade.account_id = account_id  # Привязываем к аккаунту пользователя
        db_trade.entry_commission = db_trade.commission
        db.add(db_trade)
        db.commit()
        db.refresh(db_trade)
        return db_trade

@app.post("/trades/import")
async def import_trades(
    file: UploadFile = File(...), 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    
    contents = await file.read()
    try:
        trades_data = import_service.parse_trade_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    imported_count = 0
    skipped_count = 0
    
    for trade_dict in trades_data:
        # Проверка дубликатов: symbol + direction + entry_at (только для этого аккаунта)
        existing = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.symbol == trade_dict['symbol'],
            models.Trade.direction == trade_dict['direction'],
            models.Trade.entry_at == trade_dict['entry_at']
        ).first()
        
        if existing:
            skipped_count += 1
            continue
        
        # Привязываем к аккаунту пользователя
        trade_dict["account_id"] = account_id
        
        # Создаем модель
        db_trade = models.Trade(**trade_dict)
        db.add(db_trade)
        imported_count += 1
    
    db.commit()
    return {"message": f"Импортировано: {imported_count}, пропущено дубликатов: {skipped_count}"}

@app.get("/trades/", response_model=list[schemas.Trade])
async def read_trades(
    skip: int = 0, 
    limit: int = 5000, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id
    ).offset(skip).limit(limit).all()
    return trades

@app.patch("/trades/{trade_id}", response_model=schemas.Trade)
async def update_trade(
    trade_id: int, 
    trade_update: schemas.TradeUpdate, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    update_data = trade_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_trade, key, value)
    
    db.commit()
    db.refresh(db_trade)
    return db_trade

@app.delete("/trades/{trade_id}")
async def delete_trade(
    trade_id: int, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    db.delete(trade)
    db.commit()
    return {"message": "Trade deleted"}

@app.patch("/trades/{trade_id}/close", response_model=schemas.Trade)
async def close_trade(
    trade_id: int, 
    trade_close: schemas.TradeClose, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    # Обновляем данные закрытия
    db_trade.exit_price = trade_close.exit_price
    db_trade.exit_at = trade_close.exit_at
    db_trade.exit_reason = trade_close.exit_reason
    
    # MAE/MFE: используем переданные значения или рассчитываем автоматически
    if trade_close.mae_price is not None:
        db_trade.mae_price = trade_close.mae_price
    if trade_close.mfe_price is not None:
        db_trade.mfe_price = trade_close.mfe_price
    
    # Если MAE/MFE не переданы, пытаемся рассчитать из исторических данных MOEX
    if db_trade.mae_price is None or db_trade.mfe_price is None:
        try:
            mae, mfe = market_data_service.calculate_mae_mfe(
                ticker=db_trade.symbol,
                direction=db_trade.direction.value,
                entry_price=float(db_trade.entry_price),
                entry_time=db_trade.entry_at,
                exit_time=trade_close.exit_at
            )
            if mae is not None and db_trade.mae_price is None:
                db_trade.mae_price = mae
            if mfe is not None and db_trade.mfe_price is None:
                db_trade.mfe_price = mfe
        except Exception as e:
            # Не критично — продолжаем без MAE/MFE
            log.warning(f"Failed to calculate MAE/MFE for trade {trade_id}: {e}")
    
    # Расчет PnL
    if db_trade.direction == models.TradeDirection.LONG:
        db_trade.pnl = (db_trade.exit_price - db_trade.entry_price) * db_trade.quantity
    else:
        db_trade.pnl = (db_trade.entry_price - db_trade.exit_price) * db_trade.quantity
    
    # AI Анализ
    trade_data = {
        "symbol": db_trade.symbol,
        "direction": db_trade.direction.value,
        "pnl": float(db_trade.pnl),
        "mae_price": float(db_trade.mae_price) if db_trade.mae_price else None,
        "mfe_price": float(db_trade.mfe_price) if db_trade.mfe_price else None,
        "notes": db_trade.notes,
        "exit_price": float(db_trade.exit_price)
    }
    db_trade.ai_analysis = await ai_service.analyze_trade_with_ai(trade_data)
        
    db.commit()
    db.refresh(db_trade)
    return db_trade

@app.get("/trades/unrealized-pnl")
async def get_unrealized_pnl(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    # 1. Get all open trades for this account
    open_trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at == None
    ).all()
    if not open_trades:
        return []
    
    # 2. Get unique tickers
    tickers = list(set(t.symbol for t in open_trades))
    
    # 3. Fetch current prices and futures specs
    current_prices = market_data_service.get_current_prices(tickers)
    futures_specs = market_data_service.get_futures_specs(tickers)
    
    results = []
    for trade in open_trades:
        current_price = current_prices.get(trade.symbol)
        if current_price:
            entry_price = float(trade.entry_price)
            quantity = float(trade.quantity)
            
            # Check if this is a futures contract with special pricing
            spec = futures_specs.get(trade.symbol)
            if spec and spec.get('stepprice') and spec.get('minstep'):
                # For futures: P&L = (current - entry) * stepprice / minstep * quantity
                stepprice = spec['stepprice']
                minstep = spec['minstep']
                price_diff = current_price - entry_price
                if trade.direction == models.TradeDirection.SHORT:
                    price_diff = -price_diff
                pnl = price_diff * (stepprice / minstep) * quantity
            else:
                # For stocks: simple calculation
                if trade.direction == models.TradeDirection.LONG:
                    pnl = (current_price - entry_price) * quantity
                else:
                    pnl = (entry_price - current_price) * quantity
            
            results.append({
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "current_price": current_price,
                "unrealized_pnl": pnl
            })
            
    return results

@app.get("/tags/")
async def get_all_tags(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Get all unique tags used in trades with their statistics."""
    account_id = get_account_id(db, current_user)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.pnl != None
    ).all()
    
    tag_stats = {}
    for t in trades:
        if not t.tags:
            continue
        for tag in t.tags:
            tag_lower = tag.lower()
            if tag_lower not in tag_stats:
                tag_stats[tag_lower] = {"tag": tag_lower, "count": 0, "pnl": 0, "wins": 0}
            tag_stats[tag_lower]["count"] += 1
            tag_stats[tag_lower]["pnl"] += float(t.pnl or 0)
            if t.pnl and t.pnl > 0:
                tag_stats[tag_lower]["wins"] += 1
    
    result = []
    for tag, data in tag_stats.items():
        result.append({
            "tag": data["tag"],
            "count": data["count"],
            "pnl": round(data["pnl"], 2),
            "win_rate": round((data["wins"] / data["count"]) * 100, 1) if data["count"] > 0 else 0
        })
    
    return sorted(result, key=lambda x: x["count"], reverse=True)

@app.get("/stats/", response_model=schemas.DashboardStats)
async def get_stats(
    period: Optional[str] = Query(None, description="Period filter: all, today, week, month, 3months, year, custom"),
    start_date: Optional[str] = Query(None, description="Start date for custom period (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date for custom period (YYYY-MM-DD)"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    limit: Optional[int] = Query(None, description="Limit to last N trades"),
    initial_deposit: Optional[float] = Query(None, description="Initial deposit for ROI calculation"),
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Get trading statistics with optional filters: time period, tag, and trade count limit."""
    account_id = get_account_id(db, current_user)
    
    # Build date filter
    date_filter = None
    now = datetime.utcnow()
    
    if period == "today":
        date_filter = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        date_filter = now - timedelta(days=7)
    elif period == "month":
        date_filter = now - timedelta(days=30)
    elif period == "3months":
        date_filter = now - timedelta(days=90)
    elif period == "year":
        date_filter = now - timedelta(days=365)
    elif period == "custom" and start_date:
        try:
            date_filter = datetime.strptime(start_date, "%Y-%m-%d")
        except ValueError:
            pass
    
    # Query trades with filter (только для текущего аккаунта)
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.pnl != None
    )
    
    if date_filter:
        # Filter by exit_at or entry_at
        query = query.filter(
            (models.Trade.exit_at >= date_filter) | 
            ((models.Trade.exit_at == None) & (models.Trade.entry_at >= date_filter))
        )
    
    if period == "custom" and end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(
                (models.Trade.exit_at < end_dt) | 
                ((models.Trade.exit_at == None) & (models.Trade.entry_at < end_dt))
            )
        except ValueError:
            pass
    
    # Get trades first, then apply tag filter and limit in Python
    all_trades = query.order_by(models.Trade.exit_at.desc()).all()
    
    # Filter by tag if specified
    if tag:
        tag_lower = tag.lower()
        all_trades = [t for t in all_trades if t.tags and any(tg.lower() == tag_lower for tg in t.tags)]
    
    # Apply limit (last N trades)
    if limit and limit > 0:
        all_trades = all_trades[:limit]
    
    trades = all_trades
    
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_pnl": 0,
            "win_rate": 0,
            "total_trades": 0,
            "profitable_trades": 0,
            "optimal_f": 0
        }
    
    # Use net_pnl if available, else pnl
    def get_pnl(t):
        return float(t.net_pnl if t.net_pnl is not None else t.pnl)
    
    total_pnl = sum(get_pnl(t) for t in trades)
    profitable_trades = len([t for t in trades if get_pnl(t) > 0])
    win_rate = (profitable_trades / total_trades) * 100
    
    # Расчет Optimal f
    pnls = [get_pnl(t) for t in trades]
    risks = [float(t.risk_amount) if t.risk_amount else float(abs(t.pnl)) for t in trades]
    opt_f_data = analytics.calculate_optimal_f(pnls, risks)
    
    # Расчет SQN
    sqn_data = analytics.calculate_sqn(pnls, risks)

    # Расчет Z-Score
    z_score_data = analytics.calculate_z_score(pnls)
    
    # Расчет Advanced Stats
    adv_stats = analytics.calculate_advanced_stats(pnls, risks)

    # Анализ MAE/MFE
    mae_mfe_data = analytics.analyze_mae_mfe(trades)
    
    # Расчет кривой эквити (требует хронологического порядка)
    sorted_trades = sorted(trades, key=lambda x: x.exit_at if x.exit_at else x.entry_at)
    pnls_sorted = [get_pnl(t) for t in sorted_trades]  # PnL в хронологическом порядке
    equity_curve = []
    current_balance = 0
    for t in sorted_trades:
        current_balance += get_pnl(t)
        equity_curve.append({
            "date": (t.exit_at if t.exit_at else t.entry_at).strftime("%Y-%m-%d %H:%M"),
            "balance": round(current_balance, 2)
        })
    
    # Расчет статистики по тегам
    tag_performance = {}
    for t in trades:
        if not t.tags:
            continue
        for tag in t.tags:
            tag_name = tag.lower()
            if tag_name not in tag_performance:
                tag_performance[tag_name] = {"pnl": 0, "total": 0, "wins": 0}
            tag_performance[tag_name]["pnl"] += get_pnl(t)
            tag_performance[tag_name]["total"] += 1
            if get_pnl(t) > 0:
                tag_performance[tag_name]["wins"] += 1
    
    tag_stats = []
    for tag, data in tag_performance.items():
        tag_stats.append({
            "tag": tag,
            "pnl": round(data["pnl"], 2),
            "win_rate": round((data["wins"] / data["total"]) * 100, 1),
            "count": data["total"]
        })
    # Сортируем по PnL (от лучших к худшим)
    tag_stats = sorted(tag_stats, key=lambda x: x["pnl"], reverse=True)
    
    # Расчет дополнительных метрик
    # Важно: drawdown и streaks требуют хронологического порядка (pnls_sorted)
    sortino_data = analytics.calculate_sharpe_sortino(pnls)
    drawdown_data = analytics.calculate_drawdown_stats(pnls_sorted)  # Используем хронологический порядок
    win_loss_data = analytics.calculate_win_loss_stats(pnls)
    streaks_data = analytics.calculate_streaks(pnls_sorted)  # Используем хронологический порядок
    tail_ratio_data = analytics.calculate_tail_ratio(pnls)
    r_distribution_data = analytics.calculate_r_distribution(pnls, risks)
    trade_duration_data = analytics.calculate_trade_duration(trades)
    
    # Monte Carlo и Time Patterns
    monte_carlo_data = analytics.monte_carlo_simulation(pnls)
    time_patterns_data = analytics.analyze_time_patterns(trades)
    
    # Calmar Ratio (нужен период торговли)
    if len(sorted_trades) >= 2:
        first_trade_date = sorted_trades[0].entry_at
        last_trade_date = sorted_trades[-1].exit_at if sorted_trades[-1].exit_at else sorted_trades[-1].entry_at
        trading_days = (last_trade_date - first_trade_date).days
        period_years = max(trading_days / 365, 0.1)
    else:
        period_years = 1.0
    calmar_data = analytics.calculate_calmar_ratio(pnls_sorted, initial_balance=initial_deposit or 100000, period_years=period_years)
    
    # Risk of Ruin
    avg_win = win_loss_data.get("avg_win", 0)
    avg_loss = abs(win_loss_data.get("avg_loss", 1))
    payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 1
    risk_of_ruin_data = analytics.calculate_risk_of_ruin(win_rate / 100, payoff_ratio)

    return {
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "optimal_f": opt_f_data.get("optimal_f", 0),
        "sqn": sqn_data,
        "z_score": z_score_data,
        "profit_factor": adv_stats.get("profit_factor", 0),
        "r_expectancy": adv_stats.get("r_expectancy", 0),
        "recovery_factor": adv_stats.get("recovery_factor", 0),
        "total_roi": round((total_pnl / initial_deposit * 100), 2) if initial_deposit and initial_deposit > 0 else 0,
        "expected_ghpr": opt_f_data.get("geometric_mean", 0),
        "sortino_ratio": sortino_data.get("sortino_ratio", 0),
        "max_drawdown_pct": drawdown_data.get("max_drawdown_pct", 0),
        "max_drawdown_abs": drawdown_data.get("max_drawdown_abs", 0),
        "current_drawdown_pct": drawdown_data.get("current_drawdown_pct", 0),
        "avg_win": win_loss_data.get("avg_win", 0),
        "avg_loss": win_loss_data.get("avg_loss", 0),
        "largest_win": win_loss_data.get("largest_win", 0),
        "largest_loss": win_loss_data.get("largest_loss", 0),
        "max_win_streak": streaks_data.get("max_win_streak", 0),
        "max_loss_streak": streaks_data.get("max_loss_streak", 0),
        "current_streak": streaks_data.get("current_streak", 0),
        "current_streak_type": streaks_data.get("current_streak_type"),
        "tail_ratio": tail_ratio_data.get("tail_ratio", 0),
        "calmar_ratio": calmar_data,
        "risk_of_ruin": risk_of_ruin_data,
        "r_distribution": r_distribution_data,
        "trade_duration": trade_duration_data,
        "monte_carlo": monte_carlo_data,
        "time_patterns": time_patterns_data,
        "mae_mfe_analysis": mae_mfe_data,
        "equity_curve": equity_curve,
        "tag_stats": tag_stats
    }

@app.get("/db-check")
def check_db(db: Session = Depends(database.get_db)):
    return {"status": "Database is connected and tables are created"}
