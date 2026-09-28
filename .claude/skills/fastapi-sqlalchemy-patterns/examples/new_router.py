"""
Пример роутера для ресурса Tags — теги, которые пользователь навешивает на сделки.

Стиль соответствует конвенциям Empirik (см. backend/routers/trades.py, accounts.py):
- prefix + tags на роутере
- response_model на каждом эндпоинте
- dependency injection через Depends в сигнатуре
- тонкий роутер: вся domain-логика в services/tag_service.py
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import auth_service
import database
import models
import schemas
from services import tag_service

router = APIRouter(prefix="/tags", tags=["tags"])


@router.get("", response_model=list[schemas.TagResponse])
def list_tags(
    limit: int = Query(50, ge=1, le=200, description="Размер страницы"),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=64, description="Поиск по имени"),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
) -> list[models.Tag]:
    return tag_service.list_tags(
        db,
        user_id=user.id,
        limit=limit,
        offset=offset,
        search=search,
    )


@router.get("/{tag_id}", response_model=schemas.TagResponse)
def get_tag(
    tag_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
) -> models.Tag:
    tag = tag_service.get_tag(db, user_id=user.id, tag_id=tag_id)
    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    return tag


@router.post(
    "",
    response_model=schemas.TagResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_tag(
    payload: schemas.TagCreate,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
) -> models.Tag:
    try:
        return tag_service.create_tag(db, user_id=user.id, data=payload)
    except IntegrityError as exc:
        # Уникальность по (user_id, name) — см. UniqueConstraint в модели Tag
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Tag '{payload.name}' already exists",
        ) from exc


@router.patch("/{tag_id}", response_model=schemas.TagResponse)
def update_tag(
    tag_id: int,
    payload: schemas.TagUpdate,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
) -> models.Tag:
    try:
        tag = tag_service.update_tag(
            db,
            user_id=user.id,
            tag_id=tag_id,
            data=payload,
        )
    except IntegrityError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Tag with this name already exists",
        ) from exc

    if tag is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    return tag


@router.delete("/{tag_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tag(
    tag_id: int,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
) -> None:
    deleted = tag_service.delete_tag(db, user_id=user.id, tag_id=tag_id)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
    # 204 No Content: тело не возвращаем
    return None
