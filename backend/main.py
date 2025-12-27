from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
import database
from sqlalchemy.orm import Session
import models
import schemas
import analytics
import ai_service
import import_service
import csv
import io
from fastapi.responses import StreamingResponse

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
    print("Registered routes:")
    for route in app.routes:
        print(f" - {route.path} ({route.name})")

@app.get("/test-docs", include_in_schema=False)
async def custom_docs():
    return {"message": "Test route works. If you see this, the server is fine."}

@app.get("/")
async def read_root():
    return {"message": "Добро пожаловать в API для ATOM!"}

@app.post("/trades/", response_model=schemas.Trade)
def create_trade(trade: schemas.TradeCreate, db: Session = Depends(database.get_db)):
    # 1. Создаем объект модели SQLAlchemy
    db_trade = models.Trade(**trade.model_dump())
    
    # 2. Сохраняем в базу
    db.add(db_trade)
    db.commit()
    db.refresh(db_trade)
    return db_trade

@app.post("/trades/import")
async def import_trades(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    contents = await file.read()
    try:
        trades_data = import_service.parse_trade_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    imported_count = 0
    for trade_dict in trades_data:
        # Добавляем account_id (пока хардкод 1, как и везде)
        trade_dict["account_id"] = 1
        
        # Создаем модель
        db_trade = models.Trade(**trade_dict)
        db.add(db_trade)
        imported_count += 1
    
    db.commit()
    return {"message": f"Successfully imported {imported_count} trades"}

@app.get("/trades/", response_model=list[schemas.Trade])
def read_trades(skip: int = 0, limit: int = 5000, db: Session = Depends(database.get_db)):
    trades = db.query(models.Trade).offset(skip).limit(limit).all()
    return trades

@app.get("/trades/export")
def export_trades(db: Session = Depends(database.get_db)):
    trades = db.query(models.Trade).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Заголовки
    writer.writerow([
        "ID", "Symbol", "Direction", "Entry Price", "Exit Price", 
        "Quantity", "PnL", "Entry At", "Exit At", "Tags", "Notes"
    ])
    
    for t in trades:
        writer.writerow([
            t.id, t.symbol, t.direction.value, t.entry_price, t.exit_price,
            t.quantity, t.pnl, t.entry_at, t.exit_at, 
            ", ".join(t.tags) if t.tags else "", t.notes
        ])
    
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=atom_trades_export.csv"}
    )

@app.delete("/trades/{trade_id}")
def delete_trade(trade_id: int, db: Session = Depends(database.get_db)):
    trade = db.query(models.Trade).filter(models.Trade.id == trade_id).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    db.delete(trade)
    db.commit()
    return {"message": "Trade deleted"}

@app.patch("/trades/{trade_id}/close", response_model=schemas.Trade)
async def close_trade(trade_id: int, trade_close: schemas.TradeClose, db: Session = Depends(database.get_db)):
    db_trade = db.query(models.Trade).filter(models.Trade.id == trade_id).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    # Обновляем данные закрытия
    db_trade.exit_price = trade_close.exit_price
    db_trade.exit_at = trade_close.exit_at
    db_trade.exit_reason = trade_close.exit_reason
    db_trade.mae_price = trade_close.mae_price
    db_trade.mfe_price = trade_close.mfe_price
    
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

@app.get("/stats/", response_model=schemas.DashboardStats)
def get_stats(db: Session = Depends(database.get_db)):
    trades = db.query(models.Trade).filter(models.Trade.pnl != None).all()
    
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_pnl": 0,
            "win_rate": 0,
            "total_trades": 0,
            "profitable_trades": 0,
            "optimal_f": 0
        }
    
    total_pnl = float(sum(t.pnl for t in trades))
    profitable_trades = len([t for t in trades if t.pnl > 0])
    win_rate = (profitable_trades / total_trades) * 100
    
    # Расчет Optimal f
    pnls = [float(t.pnl) for t in trades]
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
    
    # Расчет кривой эквити
    sorted_trades = sorted(trades, key=lambda x: x.exit_at if x.exit_at else x.entry_at)
    equity_curve = []
    current_balance = 0
    for t in sorted_trades:
        current_balance += float(t.pnl)
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
            tag = tag.lower()
            if tag not in tag_performance:
                tag_performance[tag] = {"pnl": 0, "total": 0, "wins": 0}
            tag_performance[tag]["pnl"] += float(t.pnl)
            tag_performance[tag]["total"] += 1
            if t.pnl > 0:
                tag_performance[tag]["wins"] += 1
    
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
        "ahpr": opt_f_data.get("geometric_mean", 0), # Используем Geometric Mean как AHPR
        "mae_mfe_analysis": mae_mfe_data,
        "equity_curve": equity_curve,
        "tag_stats": tag_stats
    }

@app.get("/db-check")
def check_db(db: Session = Depends(database.get_db)):
    return {"status": "Database is connected and tables are created"}
