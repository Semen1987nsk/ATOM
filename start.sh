#!/bin/bash

# ATOM - Start Script
# Запускает backend и frontend в фоновом режиме

echo "🚀 ATOM - Запуск сервисов..."
echo "================================"

# Останавливаем старые процессы
echo "⏹️  Останавливаю старые процессы..."
pkill -f "uvicorn main:app" 2>/dev/null
pkill -f "next dev" 2>/dev/null
sleep 1

# Создаём директорию для логов
mkdir -p /workspaces/ATOM/logs

# Запускаем Backend
echo "🔧 Запускаю Backend (порт 8000)..."
cd /workspaces/ATOM/backend
nohup python -m uvicorn main:app --host 0.0.0.0 --port 8000 > /workspaces/ATOM/logs/backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

# Ждём запуска backend
sleep 2

# Проверяем backend
if curl -s http://localhost:8000/ > /dev/null; then
    echo "   ✅ Backend запущен успешно!"
else
    echo "   ❌ Backend не отвечает, проверьте логи: logs/backend.log"
fi

# Запускаем Frontend
echo "🎨 Запускаю Frontend (порт 3000)..."
cd /workspaces/ATOM/frontend
nohup npm run dev > /workspaces/ATOM/logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"

# Ждём запуска frontend
sleep 3

# Проверяем frontend
if curl -s http://localhost:3000/ > /dev/null; then
    echo "   ✅ Frontend запущен успешно!"
else
    echo "   ⏳ Frontend запускается... подождите несколько секунд"
fi

echo ""
echo "================================"
echo "🎉 ATOM готов к работе!"
echo ""
echo "📍 Frontend: http://localhost:3000"
echo "📍 Backend:  http://localhost:8000"
echo "📍 API Docs: http://localhost:8000/docs"
echo ""
echo "📋 Логи:"
echo "   Backend:  tail -f logs/backend.log"
echo "   Frontend: tail -f logs/frontend.log"
echo ""
echo "⏹️  Остановить: ./stop.sh"
echo "================================"
