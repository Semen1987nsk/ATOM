#!/bin/bash

# Empirik - Stop Script
# Останавливает все сервисы

echo "⏹️  Empirik - Остановка сервисов..."
echo "================================"

# Останавливаем Backend
echo "🔧 Останавливаю Backend..."
pkill -f "uvicorn main:app" 2>/dev/null && echo "   ✅ Backend остановлен" || echo "   ℹ️  Backend не был запущен"

# Останавливаем Frontend
echo "🎨 Останавливаю Frontend..."
pkill -f "next dev" 2>/dev/null && echo "   ✅ Frontend остановлен" || echo "   ℹ️  Frontend не был запущен"

echo ""
echo "================================"
echo "✅ Все сервисы остановлены"
echo "🚀 Запустить: ./start.sh"
echo "================================"
