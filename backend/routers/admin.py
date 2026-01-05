"""
Admin Router — управление пользователями, аналитика, статистика
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

import database
import models
import schemas
import auth_service
import admin_service
import blog_service
from logger import get_logger

log = get_logger("admin")

router = APIRouter(prefix="/admin", tags=["admin"])


def require_admin(current_user: models.User = Depends(auth_service.get_current_user)):
    """Dependency для проверки прав администратора"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Требуются права администратора"
        )
    return current_user


# ==================== STATS ENDPOINTS ====================

@router.get("/stats")
def admin_get_stats(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Основные метрики для дашборда администратора"""
    return admin_service.get_overview_stats(db)


@router.get("/users")
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


@router.get("/registration-sources")
def admin_get_registration_sources(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Распределение пользователей по источникам регистрации"""
    return admin_service.get_registration_sources(db)


@router.get("/utm-analytics")
def admin_get_utm_analytics(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Аналитика UTM меток"""
    return admin_service.get_utm_analytics(db)


@router.get("/growth")
def admin_get_growth(
    days: int = 30,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """График роста пользователей"""
    return admin_service.get_user_growth(db, days)


@router.get("/cohorts")
def admin_get_cohorts(
    weeks: int = 8,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Когортный анализ retention"""
    return admin_service.get_cohort_retention(db, weeks)


@router.get("/power-users")
def admin_get_power_users(
    limit: int = 20,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Топ активных пользователей"""
    return admin_service.get_power_users(db, limit)


@router.get("/inactive-users")
def admin_get_inactive_users(
    days: int = 30,
    limit: int = 50,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Неактивные пользователи (churn risk)"""
    return admin_service.get_inactive_users(db, days, limit)


@router.get("/funnel")
def admin_get_funnel(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Воронка конверсии"""
    return admin_service.get_conversion_funnel(db)


# ==================== USER MANAGEMENT ====================

@router.post("/users/{user_id}/toggle-admin")
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


@router.post("/users/{user_id}/toggle-active")
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


# ==================== REVENUE ====================

@router.get("/revenue")
def admin_get_revenue(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Метрики по выручке и платным подпискам"""
    return admin_service.get_revenue_stats(db)


@router.get("/revenue-growth")
def admin_get_revenue_growth(
    days: int = 30,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """График выручки по дням"""
    return admin_service.get_revenue_growth(db, days)


@router.get("/subscription-analytics")
def admin_get_subscription_analytics(
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Аналитика по подпискам"""
    return admin_service.get_subscription_analytics(db)


@router.get("/top-paying-users")
def admin_get_top_paying_users(
    limit: int = 10,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Топ платящих пользователей"""
    return admin_service.get_top_paying_users(db, limit)


# ==================== ADMIN BLOG ENDPOINTS ====================

@router.get("/articles", tags=["blog"])
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


@router.get("/articles/{article_id}", tags=["blog"])
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


@router.post("/articles", tags=["blog"])
def admin_create_article(
    article_data: schemas.ArticleCreate,
    admin: models.User = Depends(require_admin),
    db: Session = Depends(database.get_db)
):
    """Создание новой статьи"""
    article = blog_service.create_article(db, article_data, admin.id)
    return blog_service.article_to_response(article, db)


@router.put("/articles/{article_id}", tags=["blog"])
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


@router.delete("/articles/{article_id}", tags=["blog"])
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


@router.post("/articles/{article_id}/publish", tags=["blog"])
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


@router.post("/articles/{article_id}/unpublish", tags=["blog"])
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
