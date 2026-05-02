"""
API для управления сетапами/стратегиями
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional

import models
import schemas
import database
import auth_service

router = APIRouter(prefix="/setups", tags=["setups"])


# get_account_id is now centralized in auth_service

@router.get("/", response_model=List[schemas.Setup])
async def get_setups(
    include_stats: bool = True,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Получить все сетапы пользователя с опциональной статистикой"""
    account_id = auth_service.get_account_id(db, current_user)
    
    setups = db.query(models.Setup).filter(
        models.Setup.account_id == account_id
    ).all()
    
    result = []
    for setup in setups:
        setup_dict = {
            "id": setup.id,
            "account_id": setup.account_id,
            "name": setup.name,
            "description": setup.description,
            "rules": setup.rules,
            "color": setup.color,
            "icon": setup.icon,
            "is_active": setup.is_active,
            "created_at": setup.created_at,
            "trades_count": 0,
            "win_rate": 0,
            "avg_pnl": 0,
            "total_pnl": 0
        }
        
        if include_stats:
            # Подсчёт статистики по сетапу
            trades = db.query(models.Trade).filter(
                models.Trade.setup_id == setup.id,
                models.Trade.exit_at != None
            ).all()
            
            if trades:
                setup_dict["trades_count"] = len(trades)
                winners = sum(1 for t in trades if t.pnl and float(t.pnl) > 0)
                setup_dict["win_rate"] = round(winners / len(trades) * 100, 1)
                total_pnl = sum(float(t.pnl) for t in trades if t.pnl)
                setup_dict["total_pnl"] = round(total_pnl, 2)
                setup_dict["avg_pnl"] = round(total_pnl / len(trades), 2)
        
        result.append(setup_dict)
    
    return result


@router.post("/", response_model=schemas.Setup)
async def create_setup(
    setup: schemas.SetupCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Создать новый сетап"""
    account_id = auth_service.get_account_id(db, current_user)
    
    # Проверяем, нет ли уже сетапа с таким названием
    existing = db.query(models.Setup).filter(
        models.Setup.account_id == account_id,
        models.Setup.name == setup.name
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Сетап с таким названием уже существует")
    
    db_setup = models.Setup(
        account_id=account_id,
        name=setup.name,
        description=setup.description,
        rules=setup.rules,
        color=setup.color,
        icon=setup.icon,
        is_active=setup.is_active
    )
    
    db.add(db_setup)
    db.commit()
    db.refresh(db_setup)
    
    return {
        "id": db_setup.id,
        "account_id": db_setup.account_id,
        "name": db_setup.name,
        "description": db_setup.description,
        "rules": db_setup.rules,
        "color": db_setup.color,
        "icon": db_setup.icon,
        "is_active": db_setup.is_active,
        "created_at": db_setup.created_at,
        "trades_count": 0,
        "win_rate": 0,
        "avg_pnl": 0,
        "total_pnl": 0
    }


@router.put("/{setup_id}", response_model=schemas.Setup)
async def update_setup(
    setup_id: int,
    setup_update: schemas.SetupUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Обновить сетап"""
    account_id = auth_service.get_account_id(db, current_user)
    
    db_setup = db.query(models.Setup).filter(
        models.Setup.id == setup_id,
        models.Setup.account_id == account_id
    ).first()
    
    if not db_setup:
        raise HTTPException(status_code=404, detail="Сетап не найден")
    
    update_data = setup_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_setup, field, value)
    
    db.commit()
    db.refresh(db_setup)
    
    # Подсчёт статистики
    trades = db.query(models.Trade).filter(
        models.Trade.setup_id == setup_id,
        models.Trade.exit_at != None
    ).all()
    
    trades_count = len(trades)
    win_rate = 0
    total_pnl = 0
    avg_pnl = 0
    
    if trades:
        winners = sum(1 for t in trades if t.pnl and float(t.pnl) > 0)
        win_rate = round(winners / len(trades) * 100, 1)
        total_pnl = sum(float(t.pnl) for t in trades if t.pnl)
        avg_pnl = round(total_pnl / len(trades), 2)
        total_pnl = round(total_pnl, 2)
    
    return {
        "id": db_setup.id,
        "account_id": db_setup.account_id,
        "name": db_setup.name,
        "description": db_setup.description,
        "rules": db_setup.rules,
        "color": db_setup.color,
        "icon": db_setup.icon,
        "is_active": db_setup.is_active,
        "created_at": db_setup.created_at,
        "trades_count": trades_count,
        "win_rate": win_rate,
        "avg_pnl": avg_pnl,
        "total_pnl": total_pnl
    }


@router.delete("/{setup_id}")
async def delete_setup(
    setup_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Удалить сетап (сделки НЕ удаляются, только обнуляется setup_id)"""
    account_id = auth_service.get_account_id(db, current_user)
    
    db_setup = db.query(models.Setup).filter(
        models.Setup.id == setup_id,
        models.Setup.account_id == account_id
    ).first()
    
    if not db_setup:
        raise HTTPException(status_code=404, detail="Сетап не найден")
    
    # Обнуляем setup_id у связанных сделок ТОЛЬКО текущего аккаунта
    db.query(models.Trade).filter(
        models.Trade.setup_id == setup_id,
        models.Trade.account_id == account_id
    ).update({"setup_id": None})
    
    db.delete(db_setup)
    db.commit()
    
    return {"message": "Сетап удалён", "id": setup_id}


# Предустановленные сетапы для быстрого старта
PRESET_SETUPS = [
    {"name": "Breakout", "icon": "🚀", "color": "#00d4aa", "description": "Пробой уровня с импульсом"},
    {"name": "Mean Reversion", "icon": "↩️", "color": "#f59e0b", "description": "Возврат к среднему"},
    {"name": "Trend Following", "icon": "📈", "color": "#3b82f6", "description": "Следование за трендом"},
    {"name": "Support/Resistance", "icon": "🛡️", "color": "#8b5cf6", "description": "Отскок от уровней"},
    {"name": "Gap Trading", "icon": "⬆️", "color": "#ec4899", "description": "Торговля гэпов"},
    {"name": "Scalping", "icon": "⚡", "color": "#06b6d4", "description": "Скальпинг на малых TF"},
]


@router.post("/init-presets")
async def init_preset_setups(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Создать предустановленные сетапы для нового пользователя"""
    account_id = auth_service.get_account_id(db, current_user)
    
    # Проверяем, есть ли уже сетапы
    existing = db.query(models.Setup).filter(
        models.Setup.account_id == account_id
    ).count()
    
    if existing > 0:
        return {"message": "Сетапы уже существуют", "created": 0}
    
    created = 0
    for preset in PRESET_SETUPS:
        db_setup = models.Setup(
            account_id=account_id,
            name=preset["name"],
            icon=preset["icon"],
            color=preset["color"],
            description=preset["description"]
        )
        db.add(db_setup)
        created += 1
    
    db.commit()
    
    return {"message": f"Создано {created} сетапов", "created": created}
