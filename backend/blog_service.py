"""
Blog Service - управление статьями блога
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc, func
from models import Article, ArticleCategory, User
from schemas import ArticleCreate, ArticleUpdate
import datetime
import re
from typing import Optional, List


def slugify(text: str) -> str:
    """Преобразует текст в URL-friendly slug"""
    # Транслитерация кириллицы
    translit_map = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
        'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
        'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
        'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
        'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
    }
    
    result = []
    for char in text.lower():
        if char in translit_map:
            result.append(translit_map[char])
        elif char.isalnum():
            result.append(char)
        elif char in ' -_':
            result.append('-')
    
    slug = ''.join(result)
    slug = re.sub(r'-+', '-', slug)  # Убираем множественные дефисы
    slug = slug.strip('-')
    return slug[:100]  # Ограничиваем длину


def get_unique_slug(db: Session, base_slug: str, exclude_id: Optional[int] = None) -> str:
    """Генерирует уникальный slug"""
    slug = base_slug
    counter = 1
    
    while True:
        query = db.query(Article).filter(Article.slug == slug)
        if exclude_id:
            query = query.filter(Article.id != exclude_id)
        
        if not query.first():
            return slug
        
        slug = f"{base_slug}-{counter}"
        counter += 1


def create_article(db: Session, article_data: ArticleCreate, author_id: int) -> Article:
    """Создание новой статьи"""
    # Генерируем slug если не указан
    slug = article_data.slug or slugify(article_data.title)
    slug = get_unique_slug(db, slug)
    
    # Преобразуем категорию
    try:
        category = ArticleCategory(article_data.category)
    except ValueError:
        category = ArticleCategory.NEWS
    
    article = Article(
        slug=slug,
        title=article_data.title,
        excerpt=article_data.excerpt,
        content=article_data.content,
        cover_image=article_data.cover_image,
        category=category,
        tags=article_data.tags,
        author_id=author_id,
        is_published=1 if article_data.is_published else 0,
        is_featured=1 if article_data.is_featured else 0,
        meta_title=article_data.meta_title,
        meta_description=article_data.meta_description,
        published_at=datetime.datetime.utcnow() if article_data.is_published else None
    )
    
    db.add(article)
    db.commit()
    db.refresh(article)
    return article


def update_article(db: Session, article_id: int, article_data: ArticleUpdate) -> Optional[Article]:
    """Обновление статьи"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return None
    
    update_data = article_data.dict(exclude_unset=True)
    
    # Обновляем slug если изменился title или slug
    if 'slug' in update_data and update_data['slug']:
        update_data['slug'] = get_unique_slug(db, slugify(update_data['slug']), article_id)
    elif 'title' in update_data and not article_data.slug:
        # Если title изменился, но slug не указан явно - не меняем slug
        pass
    
    # Преобразуем категорию
    if 'category' in update_data:
        try:
            update_data['category'] = ArticleCategory(update_data['category'])
        except ValueError:
            del update_data['category']
    
    # Преобразуем bool в int
    if 'is_published' in update_data:
        was_published = article.is_published
        update_data['is_published'] = 1 if update_data['is_published'] else 0
        # Устанавливаем дату публикации при первой публикации
        if update_data['is_published'] == 1 and not was_published:
            update_data['published_at'] = datetime.datetime.utcnow()
    
    if 'is_featured' in update_data:
        update_data['is_featured'] = 1 if update_data['is_featured'] else 0
    
    for key, value in update_data.items():
        setattr(article, key, value)
    
    article.updated_at = datetime.datetime.utcnow()
    db.commit()
    db.refresh(article)
    return article


def delete_article(db: Session, article_id: int) -> bool:
    """Удаление статьи"""
    article = db.query(Article).filter(Article.id == article_id).first()
    if not article:
        return False
    
    db.delete(article)
    db.commit()
    return True


def get_article_by_id(db: Session, article_id: int) -> Optional[Article]:
    """Получение статьи по ID"""
    return db.query(Article).filter(Article.id == article_id).first()


def get_article_by_slug(db: Session, slug: str, increment_views: bool = True) -> Optional[Article]:
    """Получение статьи по slug"""
    article = db.query(Article).filter(Article.slug == slug).first()
    
    if article and increment_views:
        article.views_count = (article.views_count or 0) + 1
        db.commit()
        db.refresh(article)
    
    return article


def get_articles(
    db: Session,
    skip: int = 0,
    limit: int = 20,
    category: Optional[str] = None,
    tag: Optional[str] = None,
    published_only: bool = True,
    featured_only: bool = False,
    search: Optional[str] = None
) -> List[Article]:
    """Получение списка статей"""
    query = db.query(Article)
    
    if published_only:
        query = query.filter(Article.is_published == 1)
    
    if featured_only:
        query = query.filter(Article.is_featured == 1)
    
    if category:
        try:
            cat = ArticleCategory(category)
            query = query.filter(Article.category == cat)
        except ValueError:
            pass
    
    if tag:
        # Поиск по тегу в JSON массиве
        query = query.filter(Article.tags.contains([tag]))
    
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Article.title.ilike(search_term)) | 
            (Article.excerpt.ilike(search_term)) |
            (Article.content.ilike(search_term))
        )
    
    return query.order_by(desc(Article.published_at), desc(Article.created_at)).offset(skip).limit(limit).all()


def get_articles_count(
    db: Session,
    category: Optional[str] = None,
    published_only: bool = True
) -> int:
    """Подсчёт статей"""
    query = db.query(func.count(Article.id))
    
    if published_only:
        query = query.filter(Article.is_published == 1)
    
    if category:
        try:
            cat = ArticleCategory(category)
            query = query.filter(Article.category == cat)
        except ValueError:
            pass
    
    return query.scalar() or 0


def get_all_tags(db: Session) -> List[str]:
    """Получение всех уникальных тегов"""
    articles = db.query(Article.tags).filter(Article.is_published == 1).all()
    tags = set()
    for article in articles:
        if article.tags:
            tags.update(article.tags)
    return sorted(list(tags))


def get_category_stats(db: Session) -> dict:
    """Статистика по категориям"""
    result = {}
    for cat in ArticleCategory:
        count = db.query(func.count(Article.id)).filter(
            Article.category == cat,
            Article.is_published == 1
        ).scalar() or 0
        result[cat.value] = count
    return result


def get_popular_articles(db: Session, limit: int = 5) -> List[Article]:
    """Популярные статьи по просмотрам"""
    return db.query(Article).filter(
        Article.is_published == 1
    ).order_by(desc(Article.views_count)).limit(limit).all()


def get_related_articles(db: Session, article: Article, limit: int = 3) -> List[Article]:
    """Похожие статьи по категории и тегам"""
    query = db.query(Article).filter(
        Article.is_published == 1,
        Article.id != article.id
    )
    
    # Сначала ищем по той же категории
    same_category = query.filter(Article.category == article.category).order_by(
        desc(Article.published_at)
    ).limit(limit).all()
    
    if len(same_category) >= limit:
        return same_category
    
    # Добавляем недостающие из других категорий
    remaining = limit - len(same_category)
    other_ids = [a.id for a in same_category]
    other = query.filter(Article.id.not_in(other_ids + [article.id])).order_by(
        desc(Article.views_count)
    ).limit(remaining).all()
    
    return same_category + other


def article_to_response(article: Article, db: Session) -> dict:
    """Преобразование статьи в ответ API"""
    author = db.query(User).filter(User.id == article.author_id).first()
    
    return {
        "id": article.id,
        "slug": article.slug,
        "title": article.title,
        "excerpt": article.excerpt,
        "content": article.content,
        "cover_image": article.cover_image,
        "category": article.category.value if article.category else "news",
        "tags": article.tags or [],
        "author_id": article.author_id,
        "author_name": author.name if author else "Admin",
        "is_published": bool(article.is_published),
        "is_featured": bool(article.is_featured),
        "views_count": article.views_count or 0,
        "likes_count": article.likes_count or 0,
        "created_at": article.created_at,
        "updated_at": article.updated_at,
        "published_at": article.published_at,
        "meta_title": article.meta_title,
        "meta_description": article.meta_description
    }


def article_to_list_item(article: Article, db: Session) -> dict:
    """Преобразование статьи в элемент списка"""
    author = db.query(User).filter(User.id == article.author_id).first()
    
    return {
        "id": article.id,
        "slug": article.slug,
        "title": article.title,
        "excerpt": article.excerpt,
        "cover_image": article.cover_image,
        "category": article.category.value if article.category else "news",
        "tags": article.tags or [],
        "author_name": author.name if author else "Admin",
        "views_count": article.views_count or 0,
        "likes_count": article.likes_count or 0,
        "created_at": article.created_at,
        "published_at": article.published_at
    }
