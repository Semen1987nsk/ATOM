"""
services/tag_service.py — domain-логика тегов.

Принципы (см. SKILL.md раздел 7):
- Сервис принимает Session как аргумент, не открывает её сам.
- Сервис коммитит/откатывает транзакцию.
- Сервис кидает IntegrityError наружу — роутер мапит в 409.
- Все запросы через select() (стиль SQLAlchemy 2.0), не db.query().
- selectinload для коллекций — защита от N+1.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

import models
import schemas


def list_tags(
    db: Session,
    *,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
) -> list[models.Tag]:
    stmt = (
        select(models.Tag)
        .where(models.Tag.user_id == user_id)
        .order_by(models.Tag.name.asc())
        .limit(limit)
        .offset(offset)
        .options(selectinload(models.Tag.trades))  # one IN-query вместо N запросов
    )
    if search:
        stmt = stmt.where(models.Tag.name.ilike(f"%{search}%"))

    return list(db.scalars(stmt).all())


def get_tag(db: Session, *, user_id: int, tag_id: int) -> models.Tag | None:
    stmt = (
        select(models.Tag)
        .where(models.Tag.id == tag_id, models.Tag.user_id == user_id)
        .options(selectinload(models.Tag.trades))
    )
    return db.scalar(stmt)


def count_tags(db: Session, *, user_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(models.Tag)
        .where(models.Tag.user_id == user_id)
    ) or 0


def create_tag(
    db: Session,
    *,
    user_id: int,
    data: schemas.TagCreate,
) -> models.Tag:
    tag = models.Tag(
        user_id=user_id,
        name=data.name.strip(),
        color=data.color,
    )
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise  # роутер замапит в 409
    db.refresh(tag)
    return tag


def update_tag(
    db: Session,
    *,
    user_id: int,
    tag_id: int,
    data: schemas.TagUpdate,
) -> models.Tag | None:
    tag = get_tag(db, user_id=user_id, tag_id=tag_id)
    if tag is None:
        return None

    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(tag, field, value)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise
    db.refresh(tag)
    return tag


def delete_tag(db: Session, *, user_id: int, tag_id: int) -> bool:
    """Удалить тег. Возвращает True если что-то удалено, False если не нашли."""
    tag = db.scalar(
        select(models.Tag).where(
            models.Tag.id == tag_id,
            models.Tag.user_id == user_id,
        )
    )
    if tag is None:
        return False

    db.delete(tag)
    db.commit()
    return True
