from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

# Путь к файлу базы данных SQLite
SQLALCHEMY_DATABASE_URL = "sqlite:///./atom.db"

# Создаем движок
# check_same_thread=False нужен только для SQLite
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# Создаем сессию для работы с БД
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Базовый класс для моделей (импортируем из models.py)
import models

def init_db():
    # Создаем все таблицы
    models.Base.metadata.create_all(bind=engine)

# Зависимость для получения сессии БД в эндпоинтах FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
