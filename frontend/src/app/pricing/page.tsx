'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/contexts/AuthContext';
import { AppShell } from '@/components/AppShell';
import { api } from '@/lib/apiClient';
import {
  Check, X, Zap, Crown, Building2, ArrowRight,
  Shield, Clock, BarChart3, Headphones,
  ChevronDown, ChevronUp
} from 'lucide-react';

const plans = [
  {
    id: 'free',
    name: 'Free',
    description: 'Для начинающих трейдеров',
    price: 0,
    period: 'навсегда',
    icon: Zap,
    color: 'from-gray-500 to-gray-600',
    borderColor: 'border-gray-500/30',
    features: [
      { text: 'До 50 сделок в месяц', included: true },
      { text: '1 торговый счёт', included: true },
      { text: 'Базовая статистика', included: true },
      { text: 'Импорт из Excel/PDF', included: true },
      { text: 'Дневник сделок', included: true },
      { text: 'AI-анализ сделок', included: false },
      { text: 'Продвинутая аналитика', included: false },
      { text: 'Экспорт отчётов', included: false },
      { text: 'Приоритетная поддержка', included: false },
    ],
    cta: 'Текущий план',
    popular: false,
  },
  {
    id: 'pro',
    name: 'Pro',
    description: 'Для активных трейдеров',
    price: 399,
    period: '/месяц',
    icon: Crown,
    color: 'bg-[var(--accent-soft)] border border-[var(--accent)]/30',
    borderColor: 'border-[var(--accent)]/50',
    features: [
      { text: 'Безлимит сделок', included: true },
      { text: 'До 5 торговых счетов', included: true },
      { text: 'Полная статистика', included: true },
      { text: 'Импорт из Excel/PDF', included: true },
      { text: 'Дневник сделок', included: true },
      { text: 'AI-анализ сделок', included: true },
      { text: 'Продвинутая аналитика', included: true },
      { text: 'Экспорт отчётов', included: true },
      { text: 'Приоритетная поддержка', included: false },
    ],
    cta: 'Выбрать Pro',
    popular: true,
  },
  {
    id: 'corporate',
    name: 'Corporate',
    description: 'Для проп-компаний и фондов',
    price: null,
    period: 'индивидуально',
    icon: Building2,
    color: 'bg-[var(--surface-2)] border border-[var(--border)]',
    borderColor: 'border-[var(--border-strong)]',
    features: [
      { text: 'Безлимит сделок', included: true },
      { text: 'Безлимит счетов', included: true },
      { text: 'Полная статистика', included: true },
      { text: 'Импорт из любых источников', included: true },
      { text: 'Дневник сделок', included: true },
      { text: 'AI-анализ сделок', included: true },
      { text: 'Продвинутая аналитика', included: true },
      { text: 'Экспорт отчётов', included: true },
      { text: 'Приоритетная поддержка 24/7', included: true },
      { text: 'API доступ', included: true },
      { text: 'Мультипользовательский доступ', included: true },
      { text: 'Персональный менеджер', included: true },
    ],
    cta: 'Связаться',
    popular: false,
  },
];

const faqs = [
  {
    q: 'Можно ли попробовать Pro бесплатно?',
    a: 'Да! При регистрации вы получаете 14 дней Pro-доступа бесплатно. Карта не требуется.',
  },
  {
    q: 'Как работает оплата?',
    a: 'Оплата списывается ежемесячно. Вы можете отменить подписку в любой момент, доступ сохранится до конца оплаченного периода.',
  },
  {
    q: 'Что будет с моими данными, если я отменю подписку?',
    a: 'Ваши данные сохраняются. При переходе на Free вы просто потеряете доступ к продвинутым функциям, но все сделки останутся.',
  },
  {
    q: 'Есть ли скидка при годовой оплате?',
    a: 'Да, при годовой оплате вы получаете 2 месяца бесплатно (10 месяцев по цене 12).',
  },
  {
    q: 'Как связаться для корпоративного тарифа?',
    a: 'Напишите нам на corp@empirik.app или заполните форму на странице контактов. Мы подберём решение под ваши задачи.',
  },
];

export default function PricingPage() {
  const { isAuthenticated } = useAuth();
  const [billingPeriod, setBillingPeriod] = useState<'monthly' | 'yearly'>('monthly');
  const [openFaq, setOpenFaq] = useState<number | null>(null);
  const [currentPlan, setCurrentPlan] = useState<string>('free');
  const [checkoutLoading, setCheckoutLoading] = useState<string | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;
    api.get<{ plan: string }>('/payments/me')
      .then((d) => setCurrentPlan(d.plan?.toLowerCase() || 'free'))
      .catch(() => {/* not logged in or backend down — оставляем free */});
  }, [isAuthenticated]);

  const getPrice = (basePrice: number | null) => {
    if (basePrice === null) return null;
    if (basePrice === 0) return 0;
    return billingPeriod === 'yearly' ? Math.round(basePrice * 10 / 12) : basePrice;
  };

  async function handleSubscribe(planId: string) {
    if (!isAuthenticated) {
      window.location.href = '/login?next=/pricing';
      return;
    }
    if (planId === 'free' || planId === 'corporate') return;
    setCheckoutLoading(planId);
    try {
      const r = await api.post<{ confirmation_url: string }>('/payments/checkout-link', {
        body: { plan: planId },
      });
      // Реальный YooKassa redirect, или stub-confirm в DEV
      window.location.href = r.confirmation_url;
    } catch (e) {
      alert('Не удалось создать оплату. Попробуйте позже.');
      console.error(e);
    } finally {
      setCheckoutLoading(null);
    }
  }

  return (
    <AppShell pageTitle="Тарифы">
    <main className="p-6 md:p-8 max-w-6xl mx-auto">
      {/* Decorative blur orbs удалены 2026-05-17 (ADR-0006 editorial rebrand). */}

      <div className="relative max-w-6xl mx-auto px-4 py-16">
        {/* Header */}
        <div className="text-center mb-12">
          <h1
            className="editorial-h1 mb-4"
            style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
          >
            Выберите свой <em>план</em>
          </h1>
          <p className="text-xl text-muted-foreground max-w-2xl mx-auto">
            Начните бесплатно и переходите на Pro, когда будете готовы к продвинутой аналитике
          </p>
        </div>

        {/* Billing Toggle */}
        <div className="flex items-center justify-center gap-4 mb-12">
          <span className={billingPeriod === 'monthly' ? 'text-foreground' : 'text-muted-foreground'}>
            Ежемесячно
          </span>
          <button
            onClick={() => setBillingPeriod(bp => bp === 'monthly' ? 'yearly' : 'monthly')}
            className={`relative w-14 h-7 rounded-full transition-colors ${
              billingPeriod === 'yearly' ? 'bg-[var(--accent)]' : 'bg-[var(--surface-2)]'
            }`}
          >
            <div className={`absolute top-1 w-5 h-5 rounded-full bg-[var(--paper-base)] transition-transform ${
              billingPeriod === 'yearly' ? 'translate-x-8' : 'translate-x-1'
            }`} />
          </button>
          <span className={billingPeriod === 'yearly' ? 'text-foreground' : 'text-muted-foreground'}>
            Ежегодно
            <span className="ml-2 text-xs bg-[var(--success-soft)] text-[var(--success)] px-2 py-0.5 rounded-[var(--radius-xs)] num">
              −17%
            </span>
          </span>
        </div>

        {/* Pricing Cards */}
        <div className="grid md:grid-cols-3 gap-6 mb-20">
          {plans.map((plan) => {
            const price = getPrice(plan.price);
            const isCurrent = currentPlan === plan.id;
            const Icon = plan.icon;

            return (
              <div
                key={plan.id}
                className={`relative cyber-card p-6 transition-colors ${
                  plan.popular ? 'border-t-2 !border-t-[var(--accent)]' : ''
                }`}
              >
                {plan.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <span className="bg-[var(--accent)] text-[var(--paper-base)] text-[10px] font-medium tracking-[0.14em] uppercase px-3 py-1 rounded-[var(--radius-xs)]">
                      Популярный
                    </span>
                  </div>
                )}

                {/* Header */}
                <div className="text-center mb-6">
                  <div className={`inline-flex p-3 rounded-[var(--radius-md)] ${plan.color} mb-4`}>
                    <Icon size={24} className="text-[var(--ink)]" />
                  </div>
                  <h3 className="text-2xl font-bold mb-1">{plan.name}</h3>
                  <p className="text-sm text-muted-foreground">{plan.description}</p>
                </div>

                {/* Price */}
                <div className="text-center mb-6">
                  {price !== null ? (
                    <>
                      <span className="text-4xl font-bold">₽{price}</span>
                      <span className="text-muted-foreground">{plan.period}</span>
                      {billingPeriod === 'yearly' && plan.price && plan.price > 0 && (
                        <div className="text-sm text-muted-foreground mt-1">
                          <span className="line-through">₽{plan.price * 12}</span>
                          <span className="text-green-400 ml-2">₽{price * 12}/год</span>
                        </div>
                      )}
                    </>
                  ) : (
                    <span className="text-2xl font-bold">{plan.period}</span>
                  )}
                </div>

                {/* CTA Button */}
                <button
                  onClick={() => handleSubscribe(plan.id)}
                  className={`w-full py-3 rounded-[var(--radius-md)] font-medium transition-colors mb-6 disabled:opacity-60 ${
                    isCurrent
                      ? 'bg-[var(--surface-2)] text-[var(--text-tertiary)] cursor-default'
                      : plan.popular
                      ? 'bg-[var(--accent)] text-[var(--paper-base)] hover:bg-[var(--accent-hover)]'
                      : 'bg-transparent border border-[var(--border-strong)] text-[var(--ink)] hover:bg-[var(--surface-hover)]'
                  }`}
                  disabled={isCurrent || checkoutLoading === plan.id}
                >
                  {isCurrent
                    ? 'Текущий план'
                    : checkoutLoading === plan.id
                    ? 'Создаём оплату…'
                    : plan.cta}
                  {!isCurrent && checkoutLoading !== plan.id && (
                    <ArrowRight size={16} className="inline ml-2" />
                  )}
                </button>

                {/* Features */}
                <ul className="space-y-3">
                  {plan.features.map((feature, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm">
                      {feature.included ? (
                        <Check size={16} className="text-green-400 mt-0.5 flex-shrink-0" />
                      ) : (
                        <X size={16} className="text-muted-foreground/50 mt-0.5 flex-shrink-0" />
                      )}
                      <span className={feature.included ? '' : 'text-muted-foreground/50'}>
                        {feature.text}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>

        {/* Trust Badges */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-20">
          {[
            { icon: Shield, text: 'Безопасные платежи', sub: 'Шифрование данных' },
            { icon: Clock, text: '14 дней бесплатно', sub: 'Попробуйте Pro' },
            { icon: BarChart3, text: '10,000+ трейдеров', sub: 'Уже с нами' },
            { icon: Headphones, text: 'Поддержка', sub: 'Ответим за 24ч' },
          ].map((item, i) => (
            <div key={i} className="text-center p-4">
              <item.icon size={32} className="mx-auto mb-2 text-purple-400" />
              <div className="font-medium">{item.text}</div>
              <div className="text-sm text-muted-foreground">{item.sub}</div>
            </div>
          ))}
        </div>

        {/* Feature Comparison Table */}
        <div className="mb-20">
          <h2 className="text-2xl font-bold text-center mb-8">Сравнение возможностей</h2>
          <div className="cyber-card overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10">
                    <th className="text-left p-4 font-medium">Возможность</th>
                    <th className="text-center p-4 font-medium">Free</th>
                    <th className="text-center p-4 font-medium text-purple-400">Pro</th>
                    <th className="text-center p-4 font-medium text-amber-400">Corporate</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Количество сделок', '50/мес', '∞', '∞'],
                    ['Торговые счета', '1', '5', '∞'],
                    ['Импорт Excel/PDF', true, true, true],
                    ['Базовая статистика', true, true, true],
                    ['AI-анализ', false, true, true],
                    ['MAE/MFE аналитика', false, true, true],
                    ['Экспорт отчётов', false, true, true],
                    ['API доступ', false, false, true],
                    ['Мультипользователи', false, false, true],
                    ['Приоритетная поддержка', false, false, true],
                  ].map((row, i) => (
                    <tr key={i} className="border-b border-white/5">
                      <td className="p-4">{row[0]}</td>
                      {[row[1], row[2], row[3]].map((cell, j) => (
                        <td key={j} className="text-center p-4">
                          {typeof cell === 'boolean' ? (
                            cell ? (
                              <Check size={16} className="mx-auto text-green-400" />
                            ) : (
                              <X size={16} className="mx-auto text-muted-foreground/30" />
                            )
                          ) : (
                            <span className={j === 1 ? 'text-purple-400 font-medium' : ''}>{cell}</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* FAQ */}
        <div className="max-w-3xl mx-auto mb-20">
          <h2 className="text-2xl font-bold text-center mb-8">Частые вопросы</h2>
          <div className="space-y-3">
            {faqs.map((faq, i) => (
              <div key={i} className="cyber-card overflow-hidden">
                <button
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                  className="w-full flex items-center justify-between p-4 text-left"
                >
                  <span className="font-medium">{faq.q}</span>
                  {openFaq === i ? (
                    <ChevronUp size={20} className="text-muted-foreground" />
                  ) : (
                    <ChevronDown size={20} className="text-muted-foreground" />
                  )}
                </button>
                {openFaq === i && (
                  <div className="px-4 pb-4 text-muted-foreground">
                    {faq.a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* CTA */}
        <div className="text-center">
          <div className="cyber-card inline-block p-8 max-w-2xl">
            <h2 className="text-2xl font-bold mb-4">Готовы улучшить свою торговлю?</h2>
            <p className="text-muted-foreground mb-6">
              Присоединяйтесь к тысячам трейдеров, которые уже используют ATOM для анализа своих сделок
            </p>
            <div className="flex flex-col sm:flex-row gap-4 justify-center">
              {isAuthenticated ? (
                <Link
                  href="/"
                  className="btn-primary px-8 py-3 text-lg inline-flex items-center justify-center gap-2"
                >
                  Перейти к дашборду
                  <ArrowRight size={18} />
                </Link>
              ) : (
                <>
                  <Link
                    href="/register"
                    className="btn-primary px-8 py-3 text-lg inline-flex items-center justify-center gap-2"
                  >
                    Начать бесплатно
                    <ArrowRight size={18} />
                  </Link>
                  <Link
                    href="/login"
                    className="btn-secondary px-8 py-3 text-lg"
                  >
                    Войти
                  </Link>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </main>
    </AppShell>
  );
}
