"""
routers.accounts — мульти-счётная поддержка.

Endpoints:
  GET   /accounts/             — список всех счетов пользователя
  POST  /accounts/              — создать новый счёт
  POST  /accounts/{id}/activate — переключиться на этот счёт
  PATCH /accounts/{id}          — переименовать
  DELETE /accounts/{id}         — удалить (если не последний)
"""
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

import database
import models
import auth_service
from sqlalchemy.orm.attributes import flag_modified

router = APIRouter(prefix="/accounts", tags=["accounts"])


class AccountOut(BaseModel):
    id: int
    name: str
    currency: str
    balance: float
    initial_balance: float
    is_active: bool

    model_config = {"from_attributes": True}


class CreateAccountIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    currency: str = Field(default="RUB", max_length=8)
    initial_balance: float = Field(default=0)


class RenameAccountIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)


def _serialize(acc: models.Account, active_id: int) -> AccountOut:
    return AccountOut(
        id=acc.id,
        name=acc.name,
        currency=acc.currency or "RUB",
        balance=float(acc.balance or 0),
        initial_balance=float(acc.initial_balance or 0),
        is_active=acc.id == active_id,
    )


@router.get("/", response_model=list[AccountOut])
def list_accounts(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    accounts = db.query(models.Account).filter(
        models.Account.user_id == current_user.id
    ).order_by(models.Account.id.asc()).all()
    active = auth_service.get_user_account(db, current_user)
    return [_serialize(a, active.id) for a in accounts]


@router.post("/", response_model=AccountOut, status_code=201)
def create_account(
    payload: CreateAccountIn,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    acc = models.Account(
        user_id=current_user.id,
        name=payload.name,
        currency=payload.currency,
        balance=payload.initial_balance,
        initial_balance=payload.initial_balance,
    )
    db.add(acc)
    db.commit()
    db.refresh(acc)
    active = auth_service.get_user_account(db, current_user)
    return _serialize(acc, active.id)


@router.post("/{account_id}/activate", response_model=AccountOut)
def activate_account(
    account_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    acc = db.query(models.Account).filter(
        models.Account.id == account_id,
        models.Account.user_id == current_user.id,
    ).first()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Счёт не найден")

    settings = current_user.settings or {}
    if not isinstance(settings, dict):
        settings = {}
    settings["active_account_id"] = account_id
    current_user.settings = settings
    flag_modified(current_user, "settings")
    db.commit()
    db.refresh(current_user)
    return _serialize(acc, account_id)


@router.patch("/{account_id}", response_model=AccountOut)
def rename_account(
    account_id: int,
    payload: RenameAccountIn,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    acc = db.query(models.Account).filter(
        models.Account.id == account_id,
        models.Account.user_id == current_user.id,
    ).first()
    if not acc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Счёт не найден")
    acc.name = payload.name
    db.commit()
    db.refresh(acc)
    active = auth_service.get_user_account(db, current_user)
    return _serialize(acc, active.id)


@router.delete("/{account_id}", status_code=204)
def delete_account(
    account_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    accs = db.query(models.Account).filter(
        models.Account.user_id == current_user.id
    ).all()
    if len(accs) <= 1:
        raise HTTPException(400, "Нельзя удалить последний счёт")

    acc = next((a for a in accs if a.id == account_id), None)
    if not acc:
        raise HTTPException(404, "Счёт не найден")

    db.delete(acc)
    # Если удалили активный — переключаем на первый оставшийся
    if (current_user.settings or {}).get("active_account_id") == account_id:
        remaining = [a for a in accs if a.id != account_id]
        new_settings = current_user.settings or {}
        new_settings["active_account_id"] = remaining[0].id
        current_user.settings = new_settings
        flag_modified(current_user, "settings")
    db.commit()
    return None
