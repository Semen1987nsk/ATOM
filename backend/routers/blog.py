"""
Blog Router — публичные эндпоинты для блога
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional

import database
import models
import blog_service

router = APIRouter(prefix="/blog", tags=["blog"])


@router.get("/articles")
def get_articles(
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    featured: bool = False,
    db: Session = Depends(database.get_db)
):
    # Enforce sane bounds
    limit = max(1, min(limit, 100))
    skip = max(0, skip)
    """Получение списка опубликованных статей"""
    articles = blog_service.get_articles(
        db, skip=skip, limit=limit, category=category,
        tag=tag, published_only=True, featured_only=featured, search=search
    )
    return [blog_service.article_to_list_item(a, db) for a in articles]


@router.get("/articles/count")
def get_articles_count(
    category: Optional[str] = None,
    db: Session = Depends(database.get_db)
):
    """Количество статей"""
    return {"count": blog_service.get_articles_count(db, category=category)}


@router.get("/categories")
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


@router.get("/tags")
def get_blog_tags(db: Session = Depends(database.get_db)):
    """Все теги блога"""
    return blog_service.get_all_tags(db)


@router.get("/popular")
def get_popular_articles(
    limit: int = 5,
    db: Session = Depends(database.get_db)
):
    """Популярные статьи"""
    articles = blog_service.get_popular_articles(db, limit)
    return [blog_service.article_to_list_item(a, db) for a in articles]


@router.get("/article/{slug}")
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
