'use client';

import { useState } from 'react';
import Link from 'next/link';
import { 
  HelpCircle, Mail, MessageCircle, ChevronDown, ChevronUp,
  ArrowLeft, Search, BookOpen, Zap, CreditCard,
  BarChart3, Shield, Settings, ExternalLink, Send
} from 'lucide-react';

interface FAQItem {
  question: string;
  answer: string;
  category: string;
}

const faqData: FAQItem[] = [
  // Начало работы
  {
    category: 'start',
    question: 'Как начать пользоваться ATOM?',
    answer: 'Зарегистрируйтесь, загрузите отчёт брокера (Excel/PDF) или добавьте сделки вручную. Система автоматически рассчитает все метрики и покажет аналитику на дашборде.'
  },
  {
    category: 'start',
    question: 'Какие брокеры поддерживаются?',
    answer: 'Мы поддерживаем отчёты большинства российских брокеров: Тинькофф, БКС, Финам, Альфа-Инвестиции, ВТБ Мои Инвестиции, Сбер Инвестор. Если вашего брокера нет — напишите в поддержку, добавим.'
  },
  {
    category: 'start',
    question: 'Как импортировать сделки?',
    answer: 'Нажмите "Импорт" на главной странице, выберите файл отчёта брокера (Excel .xlsx или PDF). Система автоматически распознает формат и загрузит все сделки.'
  },
  
  // Метрики
  {
    category: 'metrics',
    question: 'Что такое Optimal f и как его использовать?',
    answer: 'Optimal f (Kelly Criterion) показывает оптимальный размер позиции для максимизации роста капитала. Рекомендуем использовать f/4 для консервативной торговли или f/2 для умеренной. Полное f — только для разгона депо.'
  },
  {
    category: 'metrics',
    question: 'Что такое Profit Factor?',
    answer: 'Profit Factor = Сумма прибылей / Сумма убытков. Значение > 1 означает прибыльную торговлю. Хороший показатель: 1.5-2.0, отличный: > 2.0.'
  },
  {
    category: 'metrics',
    question: 'Что такое SQN (System Quality Number)?',
    answer: 'SQN — показатель качества торговой системы по Van Tharp. < 1.6 — плохо, 1.6-2.0 — средне, 2.0-3.0 — хорошо, > 3.0 — отлично. Требуется минимум 30 сделок для точного расчёта.'
  },
  {
    category: 'metrics',
    question: 'Что такое MAE и MFE?',
    answer: 'MAE (Maximum Adverse Excursion) — максимальная просадка против позиции. MFE (Maximum Favorable Excursion) — максимальное движение в нашу сторону. Помогает оценить качество входов и выходов.'
  },
  
  // Тарифы
  {
    category: 'billing',
    question: 'Чем отличается Pro от Free?',
    answer: 'Free: до 50 сделок/месяц, 1 счёт, базовая статистика. Pro (399₽/мес): безлимит сделок, до 5 счетов, AI-анализ, продвинутая аналитика, экспорт отчётов.'
  },
  {
    category: 'billing',
    question: 'Как оплатить подписку?',
    answer: 'Перейдите в Профиль → Улучшить до Pro. Принимаем карты Visa, Mastercard, МИР. Оплата через безопасный платёжный шлюз.'
  },
  {
    category: 'billing',
    question: 'Можно ли вернуть деньги?',
    answer: 'Да, в течение 14 дней с момента оплаты. Напишите на support@eqio.app с указанием email аккаунта.'
  },
  {
    category: 'billing',
    question: 'Есть ли пробный период?',
    answer: 'Да! При регистрации вы получаете 14 дней Pro-доступа бесплатно. Карта не требуется.'
  },
  
  // Безопасность
  {
    category: 'security',
    question: 'Безопасно ли хранить данные о сделках?',
    answer: 'Да. Все данные шифруются при передаче (HTTPS/TLS) и хранении. Мы не имеем доступа к вашим брокерским счетам — только к загруженным отчётам.'
  },
  {
    category: 'security',
    question: 'Как удалить свой аккаунт?',
    answer: 'Напишите на support@eqio.app с просьбой об удалении. Мы удалим все ваши данные в течение 24 часов.'
  },
  
  // Технические
  {
    category: 'technical',
    question: 'Почему не загружается отчёт?',
    answer: 'Проверьте формат файла (Excel .xlsx или PDF). Убедитесь, что это оригинальный отчёт брокера без изменений. Если проблема сохраняется — отправьте файл в поддержку.'
  },
  {
    category: 'technical',
    question: 'Как редактировать сделку?',
    answer: 'Перейдите в Историю сделок, найдите нужную сделку и нажмите на иконку редактирования (карандаш). Внесите изменения и сохраните.'
  },
];

const categories = [
  { id: 'all', label: 'Все', icon: HelpCircle },
  { id: 'start', label: 'Начало работы', icon: Zap },
  { id: 'metrics', label: 'Метрики', icon: BarChart3 },
  { id: 'billing', label: 'Тарифы и оплата', icon: CreditCard },
  { id: 'security', label: 'Безопасность', icon: Shield },
  { id: 'technical', label: 'Технические', icon: Settings },
];

export default function HelpPage() {
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [activeCategory, setActiveCategory] = useState('all');

  const filteredFaq = faqData.filter(item => {
    const matchesSearch = searchQuery === '' || 
      item.question.toLowerCase().includes(searchQuery.toLowerCase()) ||
      item.answer.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesCategory = activeCategory === 'all' || item.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  return (
    <main className="min-h-screen relative overflow-hidden">
      {/* Background */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-background to-cyan-500/5" />
      <div className="absolute top-40 right-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl" />
      <div className="absolute bottom-20 left-1/4 w-80 h-80 bg-purple-500/10 rounded-full blur-3xl" />

      <div className="relative max-w-5xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center gap-4 mb-8">
          <Link 
            href="/" 
            className="p-2 hover:bg-secondary rounded-lg transition-colors"
          >
            <ArrowLeft size={20} />
          </Link>
          <div>
            <h1 className="text-3xl font-bold flex items-center gap-3">
              <HelpCircle className="text-cyan-400" />
              Центр помощи
            </h1>
            <p className="text-muted-foreground">
              Ответы на частые вопросы и контакты поддержки
            </p>
          </div>
        </div>

        {/* Search */}
        <div className="relative mb-8">
          <Search size={20} className="absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Поиск по вопросам..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-12 pr-4 py-4 bg-secondary/50 border border-white/10 rounded-xl
                     text-lg focus:outline-none focus:ring-2 focus:ring-cyan-500/50 focus:border-cyan-500
                     transition-all"
          />
        </div>

        {/* Quick Contact Cards */}
        <div className="grid md:grid-cols-3 gap-4 mb-10">
          <a
            href="mailto:support@eqio.app"
            className="cyber-card p-5 hover:border-cyan-500/50 transition-all group"
          >
            <div className="flex items-center gap-4">
              <div className="p-3 bg-cyan-500/20 rounded-xl group-hover:bg-cyan-500/30 transition-colors">
                <Mail size={24} className="text-cyan-400" />
              </div>
              <div>
                <h3 className="font-bold">Email</h3>
                <p className="text-sm text-muted-foreground">support@eqio.app</p>
                <p className="text-xs text-cyan-400 mt-1">Ответим за 24 часа</p>
              </div>
            </div>
          </a>

          <a
            href="https://t.me/atom_support_bot"
            target="_blank"
            rel="noopener noreferrer"
            className="cyber-card p-5 hover:border-blue-500/50 transition-all group"
          >
            <div className="flex items-center gap-4">
              <div className="p-3 bg-blue-500/20 rounded-xl group-hover:bg-blue-500/30 transition-colors">
                <Send size={24} className="text-blue-400" />
              </div>
              <div>
                <h3 className="font-bold">Telegram</h3>
                <p className="text-sm text-muted-foreground">@atom_support_bot</p>
                <p className="text-xs text-blue-400 mt-1">Быстрые ответы</p>
              </div>
            </div>
          </a>

          <Link
            href="/manual"
            className="cyber-card p-5 hover:border-purple-500/50 transition-all group"
          >
            <div className="flex items-center gap-4">
              <div className="p-3 bg-purple-500/20 rounded-xl group-hover:bg-purple-500/30 transition-colors">
                <BookOpen size={24} className="text-purple-400" />
              </div>
              <div>
                <h3 className="font-bold">Документация</h3>
                <p className="text-sm text-muted-foreground">Руководство пользователя</p>
                <p className="text-xs text-purple-400 mt-1">Подробные инструкции</p>
              </div>
            </div>
          </Link>
        </div>

        {/* Category Tabs */}
        <div className="flex flex-wrap gap-2 mb-6">
          {categories.map(cat => {
            const Icon = cat.icon;
            return (
              <button
                key={cat.id}
                onClick={() => setActiveCategory(cat.id)}
                className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm transition-all ${
                  activeCategory === cat.id
                    ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                    : 'bg-secondary/50 text-muted-foreground hover:bg-secondary hover:text-foreground'
                }`}
              >
                <Icon size={16} />
                {cat.label}
              </button>
            );
          })}
        </div>

        {/* FAQ List */}
        <div className="space-y-3 mb-12">
          {filteredFaq.length === 0 ? (
            <div className="cyber-card p-8 text-center">
              <HelpCircle size={48} className="mx-auto mb-4 text-muted-foreground/30" />
              <p className="text-muted-foreground">
                Ничего не найдено. Попробуйте другой запрос или напишите нам.
              </p>
            </div>
          ) : (
            filteredFaq.map((item, index) => (
              <div key={index} className="cyber-card overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === index ? null : index)}
                  className="w-full flex items-center justify-between p-4 text-left hover:bg-white/5 transition-colors"
                >
                  <span className="font-medium pr-4">{item.question}</span>
                  {openFaq === index ? (
                    <ChevronUp size={20} className="text-cyan-400 flex-shrink-0" />
                  ) : (
                    <ChevronDown size={20} className="text-muted-foreground flex-shrink-0" />
                  )}
                </button>
                {openFaq === index && (
                  <div className="px-4 pb-4 text-muted-foreground border-t border-white/5 pt-3">
                    {item.answer}
                  </div>
                )}
              </div>
            ))
          )}
        </div>

        {/* Still need help? */}
        <div className="cyber-card p-8 text-center border-cyan-500/20">
          <MessageCircle size={48} className="mx-auto mb-4 text-cyan-400" />
          <h2 className="text-xl font-bold mb-2">Не нашли ответ?</h2>
          <p className="text-muted-foreground mb-6 max-w-md mx-auto">
            Наша команда поддержки готова помочь. Напишите нам и мы ответим в кратчайшие сроки.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <a
              href="mailto:support@eqio.app"
              className="btn-primary inline-flex items-center justify-center gap-2"
            >
              <Mail size={18} />
              Написать на email
            </a>
            <a
              href="https://t.me/atom_support_bot"
              target="_blank"
              rel="noopener noreferrer"
              className="btn-secondary inline-flex items-center justify-center gap-2"
            >
              <Send size={18} />
              Telegram бот
              <ExternalLink size={14} />
            </a>
          </div>
        </div>

        {/* Footer note */}
        <p className="text-center text-sm text-muted-foreground mt-8">
          Время ответа: Email — до 24 часов, Telegram — до 2 часов в рабочее время (10:00-19:00 MSK)
        </p>
      </div>
    </main>
  );
}
