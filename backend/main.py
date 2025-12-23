from fastapi import FastAPI, Depends, HTTPException
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
import database
from sqlalchemy.orm import Session
import models
import schemas
import analytics

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
    allow_origins=["*"],
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

@app.get("/trades/", response_model=list[schemas.Trade])
def read_trades(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    trades = db.query(models.Trade).offset(skip).limit(limit).all()
    return trades

@app.patch("/trades/{trade_id}/close", response_model=schemas.Trade)
def close_trade(trade_id: int, trade_close: schemas.TradeClose, db: Session = Depends(database.get_db)):
    db_trade = db.query(models.Trade).filter(models.Trade.id == trade_id).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    # Обновляем данные закрытия
    db_trade.exit_price = trade_close.exit_price
    db_trade.exit_at = trade_close.exit_at
    db_trade.mae_price = trade_close.mae_price
    db_trade.mfe_price = trade_close.mfe_price
    
    # Расчет PnL
    if db_trade.direction == models.TradeDirection.LONG:
        db_trade.pnl = (db_trade.exit_price - db_trade.entry_price) * db_trade.quantity
    else:
        db_trade.pnl = (db_trade.entry_price - db_trade.exit_price) * db_trade.quantity
        
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
    
    total_pnl = sum(t.pnl for t in trades)
    profitable_trades = len([t for t in trades if t.pnl > 0])
    win_rate = (profitable_trades / total_trades) * 100
    
    # Расчет Optimal f
    pnls = [float(t.pnl) for t in trades]
    risks = [float(t.risk_amount) if t.risk_amount else float(abs(t.pnl)) for t in trades]
    opt_f_data = analytics.calculate_optimal_f(pnls, risks)
    
    # Анализ MAE/MFE
    mae_mfe_data = analytics.analyze_mae_mfe(trades)
    
    return {
        "total_pnl": total_pnl,
        "win_rate": win_rate,
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "optimal_f": opt_f_data.get("optimal_f", 0),
        "mae_mfe_analysis": mae_mfe_data
    }

@app.get("/db-check")
def check_db(db: Session = Depends(database.get_db)):
    return {"status": "Database is connected and tables are created"}
