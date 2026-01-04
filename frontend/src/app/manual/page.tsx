'use client';

import Link from 'next/link';
import { ArrowLeft, Zap, Activity, Target, TrendingUp, BookOpen, AlertTriangle, GitGraph, Shield, Skull, Dice5, Clock, Calendar, BarChart3, Flame, Scale, TrendingDown, Sparkles, Crown, Brain, Rocket, Repeat, Tag, DollarSign, Gauge } from 'lucide-react';
import ThemeToggle from '@/components/ThemeToggle';

export default function Manual() {
  return (
    <main className="min-h-screen p-8 max-w-5xl mx-auto">
      {/* Navigation */}
      <div className="flex justify-between items-center mb-8">
        <Link href="/" className="inline-flex items-center gap-2 text-accent hover:text-foreground transition-colors font-mono text-xs uppercase tracking-widest">
          <ArrowLeft size={14} /> Вернуться к терминалу
        </Link>
        <ThemeToggle />
      </div>

      {/* Hero Section */}
      <header className="mb-16 relative">
        <div className="absolute -top-10 -left-10 w-40 h-40 bg-accent/10 rounded-full blur-3xl" />
        <div className="absolute top-0 right-0 w-32 h-32 bg-purple-500/10 rounded-full blur-3xl" />
        
        <div className="relative">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-accent/20 rounded-lg">
              <Brain className="text-accent" size={24} />
            </div>
            <span className="text-xs font-mono uppercase tracking-[0.3em] text-accent/70">Полное руководство</span>
          </div>
          
          <h1 className="text-5xl md:text-6xl font-black tracking-tighter mb-4">
            СЕКРЕТНОЕ <span className="text-accent">ОРУЖИЕ</span>
            <br />
            <span className="text-3xl md:text-4xl opacity-60">ПРОФЕССИОНАЛЬНЫХ ТРЕЙДЕРОВ</span>
          </h1>
          
          <p className="text-lg opacity-70 max-w-2xl mb-8 leading-relaxed">
            Эти индикаторы используют хедж-фонды с миллиардными активами. 
            Теперь они доступны вам. Узнайте, как <span className="text-accent font-bold">превратить хаос в систему</span> и 
            начать торговать как профессионал.
          </p>

          {/* Stats Showcase */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
            <div className="cyber-card p-4 text-center border-accent/30">
              <div className="text-3xl font-black text-accent">12+</div>
              <div className="text-[10px] font-mono uppercase opacity-50">Индикаторов</div>
            </div>
            <div className="cyber-card p-4 text-center">
              <div className="text-3xl font-black text-green-400">3x</div>
              <div className="text-[10px] font-mono uppercase opacity-50">Рост прибыли*</div>
            </div>
            <div className="cyber-card p-4 text-center">
              <div className="text-3xl font-black text-purple-400">−70%</div>
              <div className="text-[10px] font-mono uppercase opacity-50">Эмоц. ошибок</div>
            </div>
            <div className="cyber-card p-4 text-center">
              <div className="text-3xl font-black text-yellow-400">∞</div>
              <div className="text-[10px] font-mono uppercase opacity-50">Спокойствие</div>
            </div>
          </div>

          <p className="text-[10px] opacity-30 font-mono">* При использовании Optimal f на исторических данных. Результаты могут отличаться.</p>
        </div>
      </header>

      {/* Table of Contents */}
      <nav className="cyber-card p-6 mb-12 bg-gradient-to-r from-accent/5 to-purple-500/5">
        <h2 className="text-sm font-mono uppercase tracking-widest mb-4 flex items-center gap-2">
          <Sparkles size={16} className="text-accent" />
          Содержание
        </h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
          <a href="#optimal-f" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Zap size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Optimal f — Формула богатства</span>
          </a>
          <a href="#sqn" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Activity size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">SQN — Рейтинг системы</span>
          </a>
          <a href="#z-score" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <GitGraph size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Z-Score — Память удачи</span>
          </a>
          <a href="#profit-factor" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <TrendingUp size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Profit Factor — Детектор лжи</span>
          </a>
          <a href="#drawdown" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <TrendingDown size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Drawdown — Анализ просадок</span>
          </a>
          <a href="#calmar-ratio" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Gauge size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Calmar Ratio — Качество доходности</span>
          </a>
          <a href="#monte-carlo" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Dice5 size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Monte Carlo — Симуляция будущего</span>
          </a>
          <a href="#risk-of-ruin" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Skull size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Risk of Ruin — Вероятность краха</span>
          </a>
          <a href="#mae-mfe" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Target size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">MAE/MFE — Оптимизация входов</span>
          </a>
          <a href="#time-patterns" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Clock size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Time Patterns — Когда торговать</span>
          </a>
          <a href="#r-expectancy" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <DollarSign size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">R-Expectancy — Ожидание прибыли</span>
          </a>
          <a href="#streaks" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Repeat size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Streaks — Серии побед/поражений</span>
          </a>
          <a href="#tags" className="flex items-center gap-2 p-2 hover:bg-accent/10 rounded transition-colors group">
            <Tag size={14} className="text-accent" />
            <span className="group-hover:text-accent transition-colors">Tags — Система тегов</span>
          </a>
        </div>
      </nav>

      <div className="space-y-16">
        {/* Optimal f */}
        <section id="optimal-f" className="cyber-card p-8 relative overflow-hidden">
          {/* Background Effects */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-accent/20 to-transparent rounded-full blur-3xl" />
          <div className="absolute -bottom-10 -left-10 w-40 h-40 bg-green-500/10 rounded-full blur-2xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-accent to-accent/50 rounded-xl shadow-lg shadow-accent/20">
                  <Zap size={28} className="text-black" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Optimal f</h2>
                    <span className="px-2 py-0.5 bg-accent/20 rounded text-[10px] font-mono text-accent animate-pulse">MUST HAVE</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">ФОРМУЛА РАЛЬФА ВИНСА • КРИТЕРИЙ КЕЛЛИ</p>
                </div>
              </div>
              <div className="text-right hidden md:block">
                <div className="text-3xl font-black text-accent">№1</div>
                <div className="text-[10px] opacity-50">по важности</div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Проблема 90% трейдеров</div>
                  <p className="text-sm opacity-80">
                    Вы зарабатываете, но счёт почти не растёт. Или рискуете по-крупному и теряете всё за пару сделок. 
                    <span className="text-white font-medium"> Большинство трейдеров торгуют «на глаз» — и это их губит.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is it */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-accent" size={18} />
                Что такое Optimal f?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-accent">Optimal f</strong> — это математически точный ответ на главный вопрос трейдинга: 
                <span className="italic text-white"> «Какой процент капитала рисковать на каждой сделке?»</span>
              </p>
              <p className="text-sm opacity-80 leading-relaxed">
                Формула разработана <strong className="text-white">Ральфом Винсом</strong> на основе легендарного критерия Келли, 
                который использовался для обыгрывания казино и оценки телекоммуникационных сигналов. 
                Optimal f находит <strong className="text-accent">точку максимального геометрического роста</strong> вашего капитала.
              </p>
            </div>

            {/* Analogy */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <Flame className="text-orange-400" size={18} />
                Аналогия: Магическая монета
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Представьте монету с преимуществом: <span className="text-green-400 font-bold">орёл (60%)</span> = вы получаете 2x ставки, 
                <span className="text-red-400 font-bold"> решка (40%)</span> = вы теряете ставку. Казалось бы, преимущество очевидно. 
                Но сколько ставить, чтобы разбогатеть быстрее всего?
              </p>
              <div className="grid md:grid-cols-3 gap-4 mb-4">
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20">
                  <div className="text-red-400 font-black text-2xl text-center mb-2">100%</div>
                  <div className="text-sm text-center opacity-80 mb-2">Агрессивный подход</div>
                  <div className="text-xs opacity-60 text-center">
                    Одна решка — и вы банкрот. Вероятность разорения после 10 бросков: <span className="text-red-400 font-bold">99.6%</span>
                  </div>
                </div>
                <div className="bg-yellow-500/10 p-4 rounded-lg border border-yellow-500/20">
                  <div className="text-yellow-400 font-black text-2xl text-center mb-2">1%</div>
                  <div className="text-sm text-center opacity-80 mb-2">Консервативный</div>
                  <div className="text-xs opacity-60 text-center">
                    Безопасно, но за 100 бросков капитал вырастет лишь на <span className="text-yellow-400 font-bold">~22%</span>
                  </div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20">
                  <div className="text-green-400 font-black text-2xl text-center mb-2">20% ✓</div>
                  <div className="text-sm text-center opacity-80 mb-2">Optimal f</div>
                  <div className="text-xs opacity-60 text-center">
                    За 100 бросков капитал вырастет в <span className="text-green-400 font-bold">~50 раз!</span>
                  </div>
                </div>
              </div>
              <p className="text-xs opacity-50 text-center italic">
                Optimal f = точка, где скорость роста капитала максимальна
              </p>
            </div>

            {/* Formula */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                📐 Формула (упрощённая)
              </h3>
              <div className="bg-accent/10 p-4 rounded-lg font-mono text-center mb-4">
                <span className="text-accent text-lg">f* = (W × R - L) / R</span>
              </div>
              <div className="grid md:grid-cols-3 gap-4 text-sm">
                <div className="text-center">
                  <div className="text-accent font-bold">W</div>
                  <div className="opacity-60">Win Rate (% побед)</div>
                  <div className="text-xs opacity-40">Пример: 0.55 (55%)</div>
                </div>
                <div className="text-center">
                  <div className="text-accent font-bold">L</div>
                  <div className="opacity-60">Loss Rate (% проигрышей)</div>
                  <div className="text-xs opacity-40">Пример: 0.45 (45%)</div>
                </div>
                <div className="text-center">
                  <div className="text-accent font-bold">R</div>
                  <div className="opacity-60">Reward/Risk Ratio</div>
                  <div className="text-xs opacity-40">Пример: 2.0 (2:1)</div>
                </div>
              </div>
              <div className="mt-4 p-3 bg-accent/5 rounded text-sm text-center">
                <span className="opacity-70">Пример: f* = (0.55 × 2 - 0.45) / 2 = </span>
                <span className="text-accent font-bold">0.325 (32.5%)</span>
              </div>
            </div>

            {/* Real Example */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                📊 Реальный пример из торговли
              </h3>
              <div className="bg-gradient-to-r from-accent/10 via-green-500/10 to-accent/10 rounded-xl p-6 border border-accent/20">
                <div className="grid md:grid-cols-2 gap-6 mb-6">
                  <div className="space-y-3">
                    <div className="text-xs font-mono uppercase tracking-widest opacity-50">Входные данные</div>
                    <div className="space-y-2">
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Win Rate:</span>
                        <span className="text-accent font-bold">58%</span>
                      </div>
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Средний выигрыш:</span>
                        <span className="text-green-400 font-bold">+3,200 ₽</span>
                      </div>
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Средний проигрыш:</span>
                        <span className="text-red-400 font-bold">−2,100 ₽</span>
                      </div>
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Risk/Reward:</span>
                        <span className="text-accent font-bold">1:1.52</span>
                      </div>
                    </div>
                  </div>
                  <div className="space-y-3">
                    <div className="text-xs font-mono uppercase tracking-widest opacity-50">Eqio рассчитывает</div>
                    <div className="bg-accent/20 p-4 rounded-lg text-center border border-accent/30">
                      <div className="text-4xl font-black text-accent">18.7%</div>
                      <div className="text-sm opacity-70">Optimal f</div>
                    </div>
                    <div className="text-xs opacity-60 text-center">
                      Это значит: при капитале 100,000 ₽ оптимальный риск на сделку = <span className="text-accent">18,700 ₽</span>
                    </div>
                  </div>
                </div>
                
                {/* Comparison table */}
                <div className="border-t border-white/10 pt-6">
                  <div className="text-center mb-4">
                    <span className="text-xs font-mono uppercase tracking-widest opacity-50">🔥 Сравнение за 100 сделок</span>
                  </div>
                  <div className="grid md:grid-cols-3 gap-4">
                    <div className="text-center p-4 bg-black/30 rounded-lg">
                      <div className="text-xs opacity-50 mb-2">Фиксированный риск 2%</div>
                      <div className="text-xl font-black">100K → 145K</div>
                      <div className="text-green-400 text-sm">+45%</div>
                    </div>
                    <div className="text-center p-4 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
                      <div className="text-xs opacity-50 mb-2">Half-Kelly (9.3%)</div>
                      <div className="text-xl font-black text-yellow-400">100K → 380K</div>
                      <div className="text-green-400 text-sm">+280%</div>
                    </div>
                    <div className="text-center p-4 bg-accent/10 rounded-lg border border-accent/30">
                      <div className="text-xs text-accent mb-2">Full Optimal f (18.7%)</div>
                      <div className="text-xl font-black text-accent">100K → 890K</div>
                      <div className="text-green-400 text-sm font-bold">+790%</div>
                    </div>
                  </div>
                  <p className="text-center text-xs opacity-50 mt-4">Те же 100 сделок. Разный sizing. Разительно разный результат.</p>
                </div>
              </div>
            </div>

            {/* Kelly Fractions */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                <Scale className="text-yellow-400" size={18} />
                Фракции Келли: как использовать на практике
              </h3>
              <p className="text-sm opacity-80 mb-4">
                Полный Optimal f даёт максимальный рост, но с <span className="text-red-400">экстремальными просадками до 70-85%</span>. 
                Профессионалы используют фракции:
              </p>
              <div className="grid md:grid-cols-4 gap-3">
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20 text-center">
                  <div className="text-red-400 font-bold text-lg">Full Kelly</div>
                  <div className="text-xs opacity-50 mb-2">100% от f*</div>
                  <div className="text-[10px] opacity-40">MAX доход</div>
                  <div className="text-[10px] opacity-40">MAX просадки</div>
                  <div className="mt-2 text-red-400 text-xs">⚠️ Только эксперты</div>
                </div>
                <div className="bg-yellow-500/10 p-4 rounded-lg border border-yellow-500/20 text-center">
                  <div className="text-yellow-400 font-bold text-lg">Half Kelly</div>
                  <div className="text-xs opacity-50 mb-2">50% от f*</div>
                  <div className="text-[10px] opacity-40">75% дохода</div>
                  <div className="text-[10px] opacity-40">50% просадок</div>
                  <div className="mt-2 text-yellow-400 text-xs">✓ Рекомендуем</div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 text-center">
                  <div className="text-green-400 font-bold text-lg">Quarter Kelly</div>
                  <div className="text-xs opacity-50 mb-2">25% от f*</div>
                  <div className="text-[10px] opacity-40">50% дохода</div>
                  <div className="text-[10px] opacity-40">25% просадок</div>
                  <div className="mt-2 text-green-400 text-xs">✓ Консервативно</div>
                </div>
                <div className="bg-accent/10 p-4 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-bold text-lg">Eighth Kelly</div>
                  <div className="text-xs opacity-50 mb-2">12.5% от f*</div>
                  <div className="text-[10px] opacity-40">25% дохода</div>
                  <div className="text-[10px] opacity-40">12% просадок</div>
                  <div className="mt-2 text-accent text-xs">Ультра-безопасно</div>
                </div>
              </div>
            </div>

            {/* When NOT to use */}
            <div className="bg-red-500/10 p-5 rounded-lg border border-red-500/20 mb-8">
              <h3 className="text-red-400 font-bold mb-3 flex items-center gap-2">
                <Skull className="text-red-400" size={18} />
                Когда Optimal f опасен
              </h3>
              <ul className="space-y-2 text-sm opacity-80">
                <li className="flex items-start gap-2">
                  <span className="text-red-400">•</span>
                  <span><strong className="text-white">Мало сделок:</strong> при менее 30 сделок статистика ненадёжна. Используйте фиксированный риск 1-2%.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">•</span>
                  <span><strong className="text-white">Изменение рынка:</strong> если рынок изменился (волатильность, тренд), пересчитайте f* на свежих данных.</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-red-400">•</span>
                  <span><strong className="text-white">Психология:</strong> если просадка в 30-50% вызывает панику — используйте Quarter Kelly.</span>
                </li>
              </ul>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-accent pl-4 py-2 mb-6">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-accent" />
                <span className="text-sm font-bold uppercase tracking-wider text-accent">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Начните с <strong className="text-white">Quarter Kelly</strong> и повышайте по мере накопления статистики</li>
                <li>📈 Пересчитывайте Optimal f каждые 50-100 сделок</li>
                <li>🎯 Используйте разные f* для разных стратегий/инструментов</li>
                <li>⚡ Eqio автоматически рассчитывает f* и показывает рекомендуемые фракции</li>
              </ul>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-accent/10 p-4 rounded-lg text-center border border-accent/20">
                <div className="text-accent font-black text-xl">f*</div>
                <div className="text-[10px] opacity-60">Optimal f</div>
                <div className="text-[8px] opacity-40 mt-1">Оптимальная доля риска</div>
              </div>
              <div className="bg-green-500/10 p-4 rounded-lg text-center border border-green-500/20">
                <div className="text-green-400 font-black text-xl">TWR</div>
                <div className="text-[10px] opacity-60">Terminal Wealth</div>
                <div className="text-[8px] opacity-40 mt-1">Итоговый капитал</div>
              </div>
              <div className="bg-purple-500/10 p-4 rounded-lg text-center border border-purple-500/20">
                <div className="text-purple-400 font-black text-xl">GHPR</div>
                <div className="text-[10px] opacity-60">Geom. HPR</div>
                <div className="text-[8px] opacity-40 mt-1">Средний рост за сделку</div>
              </div>
            </div>
          </div>
        </section>

        {/* SQN */}
        <section id="sqn" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 -right-20 w-60 h-60 bg-purple-500/15 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-purple-500 to-purple-700 rounded-xl shadow-lg shadow-purple-500/20">
                  <Activity size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">SQN</h2>
                    <span className="px-2 py-0.5 bg-purple-500/20 rounded text-[10px] font-mono text-purple-400">VAN THARP</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">SYSTEM QUALITY NUMBER • РЕЙТИНГ ВАШЕЙ СИСТЕМЫ</p>
                </div>
              </div>
              <div className="text-right hidden md:block">
                <div className="text-3xl font-black text-purple-400">№2</div>
                <div className="text-[10px] opacity-50">по важности</div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Знакомая ситуация?</div>
                  <p className="text-sm opacity-80">
                    Стратегия прибыльная на бумаге, но вы постоянно её нарушаете. Не выдерживаете просадки, 
                    выходите раньше времени, увеличиваете риск после убытков. 
                    <span className="text-white font-medium"> Проблема не в стратегии — проблема в её «торгуемости».</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is SQN */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-purple-400" size={18} />
                Что такое SQN?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-purple-400">SQN (System Quality Number)</strong> — это индикатор, созданный 
                легендарным трейдером и психологом <strong className="text-white">Ваном Тарпом</strong>. 
                Он измеряет не просто прибыльность, а <span className="italic text-purple-400">насколько комфортно 
                торговать вашу систему</span>.
              </p>
              <p className="text-sm opacity-80 leading-relaxed">
                Представьте две стратегии с одинаковой доходностью 50% годовых. Первая даёт стабильные +4% в месяц. 
                Вторая: +30%, -25%, +40%, -35%... Математически они равны, но психологически — небо и земля. 
                <strong className="text-white"> SQN измеряет эту разницу числом.</strong>
              </p>
            </div>

            {/* Analogy */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                ✈️ Аналогия: Путешествие из А в Б
              </h3>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-red-500/10 p-5 rounded-lg border border-red-500/20">
                  <div className="font-bold text-red-400 mb-2 text-lg">SQN &lt; 1.6 — Старый джип по болоту</div>
                  <p className="text-sm opacity-70 mb-3">
                    Трясёт, укачивает, застреваете в грязи (просадки). Каждый километр — испытание нервов. 
                    Доедете... может быть. Если не сдадитесь.
                  </p>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-red-400">●</span>
                    <span className="opacity-50">80% водителей бросают машину посреди дороги</span>
                  </div>
                </div>
                <div className="bg-green-500/10 p-5 rounded-lg border border-green-500/20">
                  <div className="font-bold text-green-400 mb-2 text-lg">SQN &gt; 3.0 — Бизнес-класс</div>
                  <p className="text-sm opacity-70 mb-3">
                    Тихо, спокойно, плавно. Вы даже не замечаете турбулентности (просадок). 
                    Приземляетесь отдохнувшим и богатым.
                  </p>
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-green-400">●</span>
                    <span className="opacity-50">99% пассажиров долетают до цели</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Formula */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                📐 Формула SQN
              </h3>
              <div className="bg-purple-500/10 p-4 rounded-lg font-mono text-center mb-4">
                <span className="text-purple-400 text-lg">SQN = (Средняя R / Стандартное отклонение R) × √N</span>
              </div>
              <div className="grid md:grid-cols-3 gap-4 text-sm">
                <div className="text-center">
                  <div className="text-purple-400 font-bold">Средняя R</div>
                  <div className="opacity-60">Средний результат сделки</div>
                  <div className="text-xs opacity-40">в единицах риска (R)</div>
                </div>
                <div className="text-center">
                  <div className="text-purple-400 font-bold">Стд. отклонение</div>
                  <div className="opacity-60">Разброс результатов</div>
                  <div className="text-xs opacity-40">«тряска» системы</div>
                </div>
                <div className="text-center">
                  <div className="text-purple-400 font-bold">√N</div>
                  <div className="opacity-60">Корень из числа сделок</div>
                  <div className="text-xs opacity-40">больше сделок = надёжнее</div>
                </div>
              </div>
              <p className="text-xs opacity-50 text-center mt-4 italic">
                * Eqio использует модифицированную формулу с ограничением √N до 100 для корректности
              </p>
            </div>

            {/* Scale with detailed descriptions */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Шкала оценки Ван Тарпа</h3>
              <div className="space-y-3">
                <div className="p-4 bg-black/30 rounded-lg border-l-4 border-red-500">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="text-red-400 font-mono font-bold text-lg">SQN &lt; 1.6</div>
                      <span className="text-red-400 font-bold">СЛАБО</span>
                    </div>
                    <div className="text-2xl">😰</div>
                  </div>
                  <p className="text-sm opacity-70 mb-2">
                    Торговать такую систему — мучение. Большие просадки, нестабильные результаты. 
                    Вы будете постоянно сомневаться и нарушать правила.
                  </p>
                  <div className="text-xs text-red-400">
                    ⚠️ Рекомендация: доработать стратегию или уменьшить размер позиции
                  </div>
                </div>

                <div className="p-4 bg-black/30 rounded-lg border-l-4 border-yellow-500">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="text-yellow-400 font-mono font-bold text-lg">1.6 — 2.0</div>
                      <span className="text-yellow-400 font-bold">СРЕДНЕ</span>
                    </div>
                    <div className="text-2xl">😐</div>
                  </div>
                  <p className="text-sm opacity-70 mb-2">
                    Рабочая лошадка. Большинство прибыльных систем находятся здесь. Торговать можно, 
                    но нужна дисциплина и контроль эмоций.
                  </p>
                  <div className="text-xs text-yellow-400">
                    💡 Рекомендация: торгуйте с консервативным риском, ведите журнал
                  </div>
                </div>

                <div className="p-4 bg-black/30 rounded-lg border-l-4 border-green-500">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="text-green-400 font-mono font-bold text-lg">2.0 — 3.0</div>
                      <span className="text-green-400 font-bold">ХОРОШО</span>
                    </div>
                    <div className="text-2xl">😊</div>
                  </div>
                  <p className="text-sm opacity-70 mb-2">
                    Отличная система! Стабильные результаты, умеренные просадки. Можно смело 
                    увеличивать капитал и торговать с комфортом.
                  </p>
                  <div className="text-xs text-green-400">
                    ✓ Рекомендация: используйте Optimal f, масштабируйте капитал
                  </div>
                </div>

                <div className="p-4 bg-black/30 rounded-lg border-l-4 border-blue-500">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="text-blue-400 font-mono font-bold text-lg">3.0 — 5.0</div>
                      <span className="text-blue-400 font-bold">ОТЛИЧНО</span>
                    </div>
                    <div className="text-2xl">🚀</div>
                  </div>
                  <p className="text-sm opacity-70 mb-2">
                    Вы нашли золотую жилу! Система генерирует стабильную прибыль с минимальным стрессом. 
                    Такие системы редки и ценны.
                  </p>
                  <div className="text-xs text-blue-400">
                    🎯 Рекомендация: защитите систему, не меняйте без веских причин
                  </div>
                </div>

                <div className="p-4 bg-gradient-to-r from-accent/20 to-purple-500/20 rounded-lg border-l-4 border-accent">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-3">
                      <div className="text-accent font-mono font-bold text-lg">SQN &gt; 5.0</div>
                      <span className="text-accent font-bold">ГРААЛЬ</span>
                    </div>
                    <div className="text-2xl">🏆</div>
                  </div>
                  <p className="text-sm opacity-70 mb-2">
                    «Печатный станок». Такие системы встречаются крайне редко. Обычно это или 
                    арбитраж, или ошибка в расчётах. Перепроверьте данные!
                  </p>
                  <div className="text-xs text-accent">
                    ⚡ Если это реально — вы нашли Грааль. Храните в секрете.
                  </div>
                </div>
              </div>
            </div>

            {/* Real Example */}
            <div className="bg-gradient-to-r from-purple-500/10 via-accent/10 to-purple-500/10 rounded-xl p-6 mb-8 border border-purple-500/20">
              <h3 className="text-white font-bold text-lg mb-4">📈 Реальный пример расчёта</h3>
              
              <div className="grid md:grid-cols-2 gap-6 mb-6">
                <div className="space-y-3">
                  <div className="text-xs font-mono uppercase tracking-widest opacity-50">Ваши данные за 50 сделок</div>
                  <div className="space-y-2">
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Прибыльных сделок:</span>
                      <span className="text-green-400 font-bold">28 (56%)</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Убыточных сделок:</span>
                      <span className="text-red-400 font-bold">22 (44%)</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Средняя прибыль:</span>
                      <span className="text-green-400 font-bold">+1.8R</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Средний убыток:</span>
                      <span className="text-red-400 font-bold">−1.0R</span>
                    </div>
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="text-xs font-mono uppercase tracking-widest opacity-50">Eqio рассчитывает</div>
                  <div className="space-y-2">
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Средняя R:</span>
                      <span className="text-purple-400 font-bold">+0.57R</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Стд. отклонение:</span>
                      <span className="text-purple-400 font-bold">1.42R</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">√50:</span>
                      <span className="text-purple-400 font-bold">7.07</span>
                    </div>
                    <div className="p-3 bg-purple-500/20 rounded border border-purple-500/30">
                      <div className="text-center">
                        <div className="text-3xl font-black text-purple-400">SQN = 2.84</div>
                        <div className="text-sm text-green-400">ХОРОШО ✓</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <p className="text-sm opacity-70 text-center">
                Вердикт: система торгуема и готова к масштабированию. Можно использовать Optimal f.
              </p>
            </div>

            {/* How to improve */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                🔧 Как улучшить SQN?
              </h3>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="font-bold text-green-400 mb-2">Увеличить числитель</div>
                  <ul className="text-sm opacity-70 space-y-1">
                    <li>• Улучшить точки входа</li>
                    <li>• Держать прибыльные сделки дольше</li>
                    <li>• Резать убытки быстрее</li>
                    <li>• Увеличить Risk/Reward ratio</li>
                  </ul>
                </div>
                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="font-bold text-accent mb-2">Уменьшить знаменатель</div>
                  <ul className="text-sm opacity-70 space-y-1">
                    <li>• Стандартизировать размер позиции</li>
                    <li>• Избегать «мартингейла»</li>
                    <li>• Торговать по чётким правилам</li>
                    <li>• Фильтровать сомнительные сетапы</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-purple-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-purple-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-purple-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 SQN &lt; 1.6 не значит, что система плохая — возможно, просто нужно торговать меньшим объёмом</li>
                <li>📊 Сравнивайте SQN разных стратегий для выбора лучшей</li>
                <li>⚠️ SQN зависит от количества сделок — минимум 30 для надёжной оценки</li>
                <li>🎯 Eqio показывает SQN в реальном времени — следите за трендом!</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Z-Score */}
        <section id="z-score" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 -left-20 w-60 h-60 bg-cyan-500/15 rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-0 w-40 h-40 bg-green-500/10 rounded-full blur-2xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-cyan-500 to-cyan-700 rounded-xl shadow-lg shadow-cyan-500/20">
                  <GitGraph size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Z-Score</h2>
                    <span className="px-2 py-0.5 bg-cyan-500/20 rounded text-[10px] font-mono text-cyan-400">СЕРИЙНОСТЬ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">СТАТИСТИКА СЕРИЙ • АНТИ-МАРТИНГЕЙЛ</p>
                </div>
              </div>
              <div className="text-right hidden md:block">
                <div className="text-3xl font-black text-cyan-400">№3</div>
                <div className="text-[10px] opacity-50">по важности</div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Знакомая ловушка?</div>
                  <p className="text-sm opacity-80">
                    После 3 убытков подряд вы увеличиваете риск — «ну точно сейчас выиграю!» — и сливаете ещё больше. 
                    Или наоборот: после 5 побед расслабляетесь и попадаете в чёрную полосу. 
                    <span className="text-white font-medium"> А что, если серии можно предсказать?</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is Z-Score */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-cyan-400" size={18} />
                Что такое Z-Score?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-cyan-400">Z-Score</strong> — это статистический показатель, который отвечает на 
                фундаментальный вопрос: <span className="italic text-white">«Есть ли у ваших сделок память?»</span>
              </p>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Другими словами: влияет ли результат предыдущей сделки на вероятность следующей? 
                Это <strong className="text-white">ключ к адаптивному риск-менеджменту</strong> — вы можете 
                увеличивать или уменьшать позицию в зависимости от текущей «полосы».
              </p>
              <div className="bg-cyan-500/10 p-4 rounded-lg border border-cyan-500/20">
                <p className="text-sm italic text-center">
                  «Если у вашей системы есть паттерн серий — вы можете его эксплуатировать. 
                  <span className="text-cyan-400 font-bold"> Это как считать карты в блэкджеке, но легально.</span>»
                </p>
              </div>
            </div>

            {/* Analogy */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                🎰 Аналогия: Два типа казино
              </h3>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-green-500/10 p-5 rounded-lg border border-green-500/20">
                  <div className="font-bold text-green-400 mb-2 text-lg">🎲 Казино «Стрики»</div>
                  <p className="text-sm opacity-70 mb-3">
                    Рулетка с памятью. Выпало красное — вероятность красного выше. Чёрное тянет чёрное.
                  </p>
                  <div className="text-xs text-green-400 font-mono p-2 bg-green-500/10 rounded">
                    W-W-W-W-L-L-L-L-W-W-W
                  </div>
                  <p className="text-xs opacity-50 mt-2">Длинные серии побед и поражений</p>
                </div>
                <div className="bg-red-500/10 p-5 rounded-lg border border-red-500/20">
                  <div className="font-bold text-red-400 mb-2 text-lg">🔀 Казино «Пила»</div>
                  <p className="text-sm opacity-70 mb-3">
                    Рулетка с анти-памятью. Выпало красное — вероятность чёрного выше. Постоянное чередование.
                  </p>
                  <div className="text-xs text-red-400 font-mono p-2 bg-red-500/10 rounded">
                    W-L-W-L-W-L-L-W-L-W-L
                  </div>
                  <p className="text-xs opacity-50 mt-2">Результаты постоянно меняются</p>
                </div>
              </div>
            </div>

            {/* Formula */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                📐 Формула Z-Score
              </h3>
              <div className="bg-cyan-500/10 p-4 rounded-lg font-mono text-center mb-4">
                <span className="text-cyan-400 text-lg">Z = (N × (R − 0.5) − P) / √(P × (P − N) / (N − 1))</span>
              </div>
              <div className="grid md:grid-cols-4 gap-4 text-sm mb-4">
                <div className="text-center">
                  <div className="text-cyan-400 font-bold">N</div>
                  <div className="opacity-60 text-xs">Общее число сделок</div>
                </div>
                <div className="text-center">
                  <div className="text-cyan-400 font-bold">R</div>
                  <div className="opacity-60 text-xs">Количество серий</div>
                </div>
                <div className="text-center">
                  <div className="text-cyan-400 font-bold">P</div>
                  <div className="opacity-60 text-xs">2 × W × L</div>
                </div>
                <div className="text-center">
                  <div className="text-cyan-400 font-bold">W, L</div>
                  <div className="opacity-60 text-xs">Кол-во побед/поражений</div>
                </div>
              </div>
              <p className="text-xs opacity-50 text-center italic">
                * Не волнуйтесь! Eqio считает это автоматически. Вам нужно только понимать интерпретацию.
              </p>
            </div>

            {/* Three Scenarios - Detailed */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Три сценария и как их использовать</h3>
              <div className="space-y-4">
                
                {/* Streaks */}
                <div className="bg-gradient-to-r from-green-500/10 to-green-500/5 p-5 rounded-lg border border-green-500/20">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-green-400 font-mono font-bold text-xl">Z &lt; −1.96</span>
                        <span className="px-2 py-0.5 bg-green-500/20 rounded text-[10px] font-mono text-green-400">СТРИКИ</span>
                      </div>
                      <div className="text-sm opacity-70">«Победы притягивают победы, поражения — поражения»</div>
                    </div>
                    <div className="text-3xl">🔥</div>
                  </div>
                  
                  <div className="grid md:grid-cols-2 gap-4 mb-4">
                    <div className="bg-black/30 p-3 rounded">
                      <div className="text-xs font-mono text-green-400 mb-2">Что происходит:</div>
                      <p className="text-sm opacity-80">
                        Ваша система имеет <strong className="text-white">положительную автокорреляцию</strong>. 
                        После победы вероятность следующей победы выше среднего. После убытка — выше вероятность убытка.
                      </p>
                    </div>
                    <div className="bg-black/30 p-3 rounded">
                      <div className="text-xs font-mono text-green-400 mb-2">Почему это бывает:</div>
                      <ul className="text-sm opacity-80 space-y-1">
                        <li>• Система работает в тренде</li>
                        <li>• Рынок фазовый (тренд/флэт)</li>
                        <li>• Психологические паттерны</li>
                      </ul>
                    </div>
                  </div>
                  
                  <div className="bg-green-500/20 p-4 rounded border border-green-500/30">
                    <div className="font-bold text-green-400 mb-2 flex items-center gap-2">
                      <Rocket size={16} /> Стратегия «Антимартингейл»
                    </div>
                    <ul className="text-sm space-y-2">
                      <li className="flex items-start gap-2">
                        <span className="text-green-400">✓</span>
                        <span><strong className="text-white">После победы:</strong> увеличивайте позицию на 25-50%. Ловите волну!</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-red-400">✗</span>
                        <span><strong className="text-white">После убытка:</strong> снижайте до минимума (25-50% от нормы). Пережидайте чёрную полосу.</span>
                      </li>
                    </ul>
                  </div>
                  
                  <div className="mt-4 p-3 bg-black/30 rounded">
                    <div className="text-xs font-mono opacity-50 mb-2">Пример:</div>
                    <p className="text-sm opacity-80">
                      Базовый риск = 1%. После 2 побед подряд → риск 1.5%. После 3 побед → 2%. 
                      После первого убытка → сразу обратно на 0.5% и ждём конца серии.
                    </p>
                  </div>
                </div>

                {/* Random */}
                <div className="bg-gradient-to-r from-gray-500/10 to-gray-500/5 p-5 rounded-lg border border-gray-500/20">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-gray-300 font-mono font-bold text-xl">−1.96 &lt; Z &lt; 1.96</span>
                        <span className="px-2 py-0.5 bg-gray-500/20 rounded text-[10px] font-mono text-gray-300">СЛУЧАЙНОСТЬ</span>
                      </div>
                      <div className="text-sm opacity-70">«Результаты независимы — как подбрасывание монеты»</div>
                    </div>
                    <div className="text-3xl">🎲</div>
                  </div>
                  
                  <div className="bg-black/30 p-3 rounded mb-4">
                    <div className="text-xs font-mono text-gray-300 mb-2">Что это значит:</div>
                    <p className="text-sm opacity-80">
                      Прошлая сделка <strong className="text-white">никак не влияет</strong> на следующую. 
                      Это самый распространённый случай. Большинство систем попадают сюда.
                    </p>
                  </div>
                  
                  <div className="bg-gray-500/20 p-4 rounded border border-gray-500/30">
                    <div className="font-bold text-gray-300 mb-2 flex items-center gap-2">
                      <Scale size={16} /> Стратегия «Постоянство»
                    </div>
                    <ul className="text-sm space-y-2">
                      <li className="flex items-start gap-2">
                        <span className="text-gray-300">•</span>
                        <span>Используйте <strong className="text-white">фиксированный процент риска</strong> на каждую сделку</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-gray-300">•</span>
                        <span>Не пытайтесь предсказать серии — это бесполезно</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-gray-300">•</span>
                        <span>Сфокусируйтесь на качестве сетапов, а не на «горячей руке»</span>
                      </li>
                    </ul>
                  </div>
                </div>

                {/* Saw */}
                <div className="bg-gradient-to-r from-red-500/10 to-red-500/5 p-5 rounded-lg border border-red-500/20">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-red-400 font-mono font-bold text-xl">Z &gt; 1.96</span>
                        <span className="px-2 py-0.5 bg-red-500/20 rounded text-[10px] font-mono text-red-400">ПИЛА</span>
                      </div>
                      <div className="text-sm opacity-70">«Результаты постоянно чередуются»</div>
                    </div>
                    <div className="text-3xl">🪚</div>
                  </div>
                  
                  <div className="grid md:grid-cols-2 gap-4 mb-4">
                    <div className="bg-black/30 p-3 rounded">
                      <div className="text-xs font-mono text-red-400 mb-2">Что происходит:</div>
                      <p className="text-sm opacity-80">
                        Ваша система имеет <strong className="text-white">отрицательную автокорреляцию</strong>. 
                        После победы выше вероятность убытка. После убытка — выше вероятность победы.
                      </p>
                    </div>
                    <div className="bg-black/30 p-3 rounded">
                      <div className="text-xs font-mono text-red-400 mb-2">Почему это бывает:</div>
                      <ul className="text-sm opacity-80 space-y-1">
                        <li>• Система работает в флэте</li>
                        <li>• Контртрендовая стратегия</li>
                        <li>• Mean-reversion подход</li>
                      </ul>
                    </div>
                  </div>
                  
                  <div className="bg-red-500/20 p-4 rounded border border-red-500/30">
                    <div className="font-bold text-red-400 mb-2 flex items-center gap-2">
                      <AlertTriangle size={16} /> Стратегия «Парадокс» (осторожно!)
                    </div>
                    <ul className="text-sm space-y-2">
                      <li className="flex items-start gap-2">
                        <span className="text-green-400">✓</span>
                        <span><strong className="text-white">После убытка:</strong> увеличивайте позицию — следующая с большей вероятностью прибыльная</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="text-red-400">✗</span>
                        <span><strong className="text-white">После победы:</strong> снижайте позицию — ждём откат</span>
                      </li>
                    </ul>
                    <p className="text-xs opacity-50 mt-3 italic">
                      ⚠️ Это контринтуитивно! Убедитесь, что Z-Score стабильно &gt; 1.96 на большой выборке.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Real Example */}
            <div className="bg-gradient-to-r from-cyan-500/10 via-accent/10 to-cyan-500/10 rounded-xl p-6 mb-8 border border-cyan-500/20">
              <h3 className="text-white font-bold text-lg mb-4">📈 Реальный пример анализа</h3>
              
              <div className="grid md:grid-cols-2 gap-6 mb-6">
                <div className="space-y-3">
                  <div className="text-xs font-mono uppercase tracking-widest opacity-50">Последовательность 40 сделок</div>
                  <div className="bg-black/30 p-3 rounded font-mono text-xs leading-relaxed">
                    <span className="text-green-400">W W W</span> <span className="text-red-400">L L</span> <span className="text-green-400">W W W W</span> <span className="text-red-400">L L L</span> <span className="text-green-400">W W</span> <span className="text-red-400">L</span> <span className="text-green-400">W W W</span> <span className="text-red-400">L L L L</span> <span className="text-green-400">W W W W W</span> <span className="text-red-400">L L</span> <span className="text-green-400">W W W</span> <span className="text-red-400">L L</span> <span className="text-green-400">W</span>
                  </div>
                  <div className="text-xs opacity-50">
                    Визуально видны длинные серии побед и поражений
                  </div>
                </div>
                <div className="space-y-3">
                  <div className="text-xs font-mono uppercase tracking-widest opacity-50">Eqio рассчитывает</div>
                  <div className="space-y-2">
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Всего сделок (N):</span>
                      <span className="text-cyan-400 font-bold">40</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Количество серий (R):</span>
                      <span className="text-cyan-400 font-bold">14</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Ожидаемые серии:</span>
                      <span className="text-cyan-400 font-bold">~20</span>
                    </div>
                    <div className="p-3 bg-green-500/20 rounded border border-green-500/30">
                      <div className="text-center">
                        <div className="text-3xl font-black text-green-400">Z = −2.47</div>
                        <div className="text-sm text-green-400">СТРИКИ ✓</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="bg-black/30 p-4 rounded">
                <div className="font-bold text-cyan-400 mb-2">💡 Рекомендация Eqio:</div>
                <p className="text-sm opacity-80">
                  Ваша система демонстрирует статистически значимый паттерн серий. Используйте 
                  <strong className="text-white"> антимартингейл</strong>: увеличивайте риск в серии побед, снижайте при убытках.
                  Потенциальный прирост доходности: <span className="text-green-400 font-bold">+15-30%</span> при том же уровне риска.
                </p>
              </div>
            </div>

            {/* Warning */}
            <div className="bg-yellow-500/10 p-5 rounded-lg border border-yellow-500/20 mb-8">
              <h3 className="text-yellow-400 font-bold mb-3 flex items-center gap-2">
                <AlertTriangle size={18} />
                Важные предупреждения
              </h3>
              <ul className="space-y-2 text-sm opacity-80">
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400">⚠️</span>
                  <span><strong className="text-white">Минимум 30 сделок:</strong> Z-Score на малой выборке ненадёжен</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400">⚠️</span>
                  <span><strong className="text-white">Z-Score меняется:</strong> пересчитывайте каждые 50-100 сделок</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-yellow-400">⚠️</span>
                  <span><strong className="text-white">Не переусердствуйте:</strong> изменяйте позицию максимум на 50%, не на 200%</span>
                </li>
              </ul>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-cyan-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-cyan-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-cyan-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Если Z-Score близок к 0 — это НЕ плохо. Это значит, что вам не нужно усложнять риск-менеджмент</li>
                <li>📊 Разные инструменты могут иметь разный Z-Score — анализируйте отдельно</li>
                <li>🎯 Комбинируйте Z-Score с Optimal f для максимальной эффективности</li>
                <li>⚡ Eqio автоматически отслеживает Z-Score и предупреждает об изменениях паттерна</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Profit Factor */}
        <section id="profit-factor" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 right-0 w-60 h-60 bg-green-500/15 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-green-500 to-green-700 rounded-xl shadow-lg shadow-green-500/20">
                  <TrendingUp size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Profit Factor</h2>
                    <span className="px-2 py-0.5 bg-green-500/20 rounded text-[10px] font-mono text-green-400">ДЕТЕКТОР ЛЖИ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">ВАЛОВАЯ ПРИБЫЛЬ / ВАЛОВОЙ УБЫТОК</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Типичное заблуждение</div>
                  <p className="text-sm opacity-80">
                    «У меня 70% прибыльных сделок — я крутой трейдер!» Но если средняя прибыль $100, а средний убыток $500 — 
                    <span className="text-white font-medium"> вы разоряетесь с улыбкой на лице.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is it */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-green-400" size={18} />
                Что такое Profit Factor?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-green-400">Profit Factor</strong> — это самый честный показатель прибыльности. 
                Он отвечает на простой вопрос: <span className="italic text-white">«На каждый потерянный рубль — сколько рублей вы зарабатываете?»</span>
              </p>
              <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 font-mono text-center">
                <span className="text-green-400 text-lg">PF = Сумма всех прибылей / Сумма всех убытков</span>
              </div>
            </div>

            {/* Real Example */}
            <div className="bg-gradient-to-r from-green-500/10 via-accent/10 to-green-500/10 rounded-xl p-6 mb-8 border border-green-500/20">
              <h3 className="text-white font-bold text-lg mb-4">📊 Примеры расчёта</h3>
              
              <div className="grid md:grid-cols-2 gap-6 mb-4">
                <div className="bg-black/30 p-4 rounded-lg border border-red-500/20">
                  <div className="text-sm font-mono text-red-400 mb-3">❌ Трейдер «Снайпер»</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-70">Win Rate:</span>
                      <span className="text-green-400 font-bold">80% (впечатляет!)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-70">Сумма прибылей:</span>
                      <span className="text-green-400">+40,000 ₽</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-70">Сумма убытков:</span>
                      <span className="text-red-400">−50,000 ₽</span>
                    </div>
                    <div className="border-t border-white/10 pt-2 mt-2">
                      <div className="flex justify-between">
                        <span className="opacity-70">Profit Factor:</span>
                        <span className="text-red-400 font-bold">0.8 (УБЫТОК!)</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="bg-black/30 p-4 rounded-lg border border-green-500/20">
                  <div className="text-sm font-mono text-green-400 mb-3">✓ Трейдер «Терпеливый»</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-70">Win Rate:</span>
                      <span className="text-yellow-400 font-bold">40% (скромно)</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-70">Сумма прибылей:</span>
                      <span className="text-green-400">+120,000 ₽</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-70">Сумма убытков:</span>
                      <span className="text-red-400">−40,000 ₽</span>
                    </div>
                    <div className="border-t border-white/10 pt-2 mt-2">
                      <div className="flex justify-between">
                        <span className="opacity-70">Profit Factor:</span>
                        <span className="text-green-400 font-bold">3.0 (ЭЛИТА!)</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              
              <p className="text-xs opacity-50 text-center italic">
                Win Rate = ничто. Profit Factor = всё. Первый трейдер разоряется, второй богатеет.
              </p>
            </div>

            {/* Scale */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📈 Шкала оценки Profit Factor</h3>
              <div className="space-y-3">
                <div className="flex items-center gap-3 p-3 bg-black/30 rounded-lg border-l-4 border-red-500">
                  <div className="w-24 text-red-400 font-mono font-bold">PF &lt; 1.0</div>
                  <div className="flex-1">
                    <span className="text-red-400 font-bold">УБЫТОК</span>
                    <span className="text-xs opacity-50 ml-2">— Система теряет деньги на дистанции</span>
                  </div>
                  <div className="text-2xl">💸</div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-black/30 rounded-lg border-l-4 border-yellow-500">
                  <div className="w-24 text-yellow-400 font-mono font-bold">1.0 — 1.5</div>
                  <div className="flex-1">
                    <span className="text-yellow-400 font-bold">СЛАБО</span>
                    <span className="text-xs opacity-50 ml-2">— Комиссии съедят прибыль</span>
                  </div>
                  <div className="text-2xl">😕</div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-black/30 rounded-lg border-l-4 border-green-500">
                  <div className="w-24 text-green-400 font-mono font-bold">1.5 — 2.0</div>
                  <div className="flex-1">
                    <span className="text-green-400 font-bold">ХОРОШО</span>
                    <span className="text-xs opacity-50 ml-2">— Рабочая система</span>
                  </div>
                  <div className="text-2xl">👍</div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-black/30 rounded-lg border-l-4 border-blue-500">
                  <div className="w-24 text-blue-400 font-mono font-bold">2.0 — 3.0</div>
                  <div className="flex-1">
                    <span className="text-blue-400 font-bold">ОТЛИЧНО</span>
                    <span className="text-xs opacity-50 ml-2">— Профессиональный уровень</span>
                  </div>
                  <div className="text-2xl">🎯</div>
                </div>
                <div className="flex items-center gap-3 p-3 bg-gradient-to-r from-accent/20 to-green-500/20 rounded-lg border-l-4 border-accent">
                  <div className="w-24 text-accent font-mono font-bold">PF &gt; 3.0</div>
                  <div className="flex-1">
                    <span className="text-accent font-bold">ЭЛИТА</span>
                    <span className="text-xs opacity-50 ml-2">— Топ 1% трейдеров</span>
                  </div>
                  <div className="text-2xl">🏆</div>
                </div>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-green-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-green-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-green-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 <strong className="text-white">PF &gt; 2.0</strong> — золотой стандарт для swing-трейдинга</li>
                <li>📊 Для скальпинга достаточно <strong className="text-white">PF 1.3-1.5</strong> из-за большого количества сделок</li>
                <li>⚠️ Если PF падает — проверьте, не увеличились ли ваши убытки (средний лосс)</li>
                <li>🎯 Eqio показывает PF в реальном времени — следите за трендом!</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Recovery Factor & Drawdown */}
        <section id="drawdown" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 -right-20 w-60 h-60 bg-red-500/15 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-red-500 to-red-700 rounded-xl shadow-lg shadow-red-500/20">
                  <TrendingDown size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Drawdown & Recovery</h2>
                    <span className="px-2 py-0.5 bg-red-500/20 rounded text-[10px] font-mono text-red-400">РИСК-МЕТРИКИ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">ПРОСАДКИ • ВОССТАНОВЛЕНИЕ • ЖИВУЧЕСТЬ</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Главный убийца трейдеров</div>
                  <p className="text-sm opacity-80">
                    Не убытки убивают — убивает <strong className="text-white">неспособность восстановиться</strong>. 
                    Просадка 50% требует 100% прибыли для выхода в ноль. Просадка 90% — 900%!
                  </p>
                </div>
              </div>
            </div>

            {/* Max Drawdown */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <TrendingDown className="text-red-400" size={18} />
                Maximum Drawdown (MDD)
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-red-400">Максимальная просадка</strong> — это наибольшее падение капитала от пика до дна. 
                Это ваш <span className="italic text-white">«худший кошмар»</span> — момент, когда вы ближе всего к сливу.
              </p>
              
              <div className="bg-black/40 rounded-xl p-6 mb-4 border border-white/10">
                <div className="text-center mb-4">
                  <span className="text-xs font-mono uppercase tracking-widest opacity-50">Пример: Эквити трейдера</span>
                </div>
                <div className="flex items-end justify-center gap-1 h-32 mb-4">
                  <div className="w-8 bg-green-500/50 rounded-t" style={{height: '40%'}}></div>
                  <div className="w-8 bg-green-500/50 rounded-t" style={{height: '60%'}}></div>
                  <div className="w-8 bg-green-500/50 rounded-t" style={{height: '80%'}}></div>
                  <div className="w-8 bg-accent rounded-t relative" style={{height: '100%'}}>
                    <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-[10px] text-accent font-mono">ПИК</div>
                  </div>
                  <div className="w-8 bg-red-500/50 rounded-t" style={{height: '70%'}}></div>
                  <div className="w-8 bg-red-500/50 rounded-t" style={{height: '50%'}}></div>
                  <div className="w-8 bg-red-500/80 rounded-t relative" style={{height: '35%'}}>
                    <div className="absolute -top-6 left-1/2 -translate-x-1/2 text-[10px] text-red-400 font-mono">ДНО</div>
                  </div>
                  <div className="w-8 bg-green-500/50 rounded-t" style={{height: '50%'}}></div>
                  <div className="w-8 bg-green-500/50 rounded-t" style={{height: '70%'}}></div>
                  <div className="w-8 bg-green-500/50 rounded-t" style={{height: '90%'}}></div>
                </div>
                <div className="text-center">
                  <span className="text-red-400 font-bold">MDD = −65%</span>
                  <span className="text-xs opacity-50 ml-2">(от пика 100K до дна 35K)</span>
                </div>
              </div>
            </div>

            {/* Recovery Table */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Таблица восстановления</h3>
              <p className="text-sm opacity-70 mb-4">
                Чем глубже просадка — тем сложнее вернуться. Математика беспощадна:
              </p>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-yellow-500/10 p-3 rounded-lg border border-yellow-500/20 text-center">
                  <div className="text-yellow-400 font-bold text-lg">−10%</div>
                  <div className="text-[10px] opacity-50 mb-1">Просадка</div>
                  <div className="text-green-400 font-bold">+11%</div>
                  <div className="text-[10px] opacity-50">Для восстановления</div>
                </div>
                <div className="bg-orange-500/10 p-3 rounded-lg border border-orange-500/20 text-center">
                  <div className="text-orange-400 font-bold text-lg">−25%</div>
                  <div className="text-[10px] opacity-50 mb-1">Просадка</div>
                  <div className="text-green-400 font-bold">+33%</div>
                  <div className="text-[10px] opacity-50">Для восстановления</div>
                </div>
                <div className="bg-red-500/10 p-3 rounded-lg border border-red-500/20 text-center">
                  <div className="text-red-400 font-bold text-lg">−50%</div>
                  <div className="text-[10px] opacity-50 mb-1">Просадка</div>
                  <div className="text-green-400 font-bold">+100%</div>
                  <div className="text-[10px] opacity-50">Для восстановления</div>
                </div>
                <div className="bg-red-500/20 p-3 rounded-lg border border-red-500/30 text-center">
                  <div className="text-red-400 font-bold text-lg">−90%</div>
                  <div className="text-[10px] opacity-50 mb-1">Просадка</div>
                  <div className="text-red-400 font-bold">+900%</div>
                  <div className="text-[10px] opacity-50">Почти невозможно</div>
                </div>
              </div>
            </div>

            {/* Recovery Factor */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <Shield className="text-green-400" size={18} />
                Recovery Factor (RF)
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-green-400">Recovery Factor</strong> показывает, насколько быстро система 
                выбирается из просадок. Формула: <span className="font-mono text-accent">Чистая прибыль / Max Drawdown</span>
              </p>
              
              <div className="grid md:grid-cols-2 gap-6 mb-4">
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20">
                  <div className="font-bold text-red-400 mb-2">RF = 1.0 (плохо)</div>
                  <p className="text-sm opacity-70 mb-2">
                    Заработали 100K, но просадка была 100K.
                  </p>
                  <p className="text-xs opacity-50">
                    Вы сидели на валидоле. Ещё немного — и слив.
                  </p>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20">
                  <div className="font-bold text-green-400 mb-2">RF = 5.0 (отлично)</div>
                  <p className="text-sm opacity-70 mb-2">
                    Заработали 100K, максимальная просадка всего 20K.
                  </p>
                  <p className="text-xs opacity-50">
                    Идеальная кривая. Стабильный рост без стресса.
                  </p>
                </div>
              </div>

              <div className="bg-accent/5 p-4 rounded-lg border border-accent/20">
                <h4 className="font-bold text-accent mb-2">💡 Правило профессионалов</h4>
                <p className="text-sm opacity-80">
                  <strong className="text-white">RF &gt; 3.0</strong> — хорошая система. 
                  <strong className="text-white"> RF &gt; 5.0</strong> — отличная. 
                  <strong className="text-white"> RF &lt; 1.0</strong> — пересмотрите риск-менеджмент!
                </p>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-red-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-red-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-red-400">Защита капитала</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Установите <strong className="text-white">максимально допустимую просадку</strong> (например, 20%) и снижайте риск при приближении</li>
                <li>📊 Если текущая просадка &gt; 50% от максимальной — уменьшите размер позиции</li>
                <li>⚠️ После просадки 30% переходите на минимальный риск до восстановления</li>
                <li>🎯 Eqio показывает текущую просадку в реальном времени</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Calmar Ratio */}
        <section id="calmar-ratio" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-gradient-to-bl from-teal-500/20 to-transparent rounded-full blur-3xl" />
          <div className="absolute -bottom-10 -left-10 w-40 h-40 bg-teal-500/10 rounded-full blur-2xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-teal-500 to-teal-700 rounded-xl shadow-lg shadow-teal-500/20">
                  <Gauge size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Calmar Ratio</h2>
                    <span className="px-2 py-0.5 bg-teal-500/20 rounded text-[10px] font-mono text-teal-400">RISK-ADJUSTED</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">ИНДИКАТОР ХЕДЖ-ФОНДОВ • ГОДОВАЯ ДОХОДНОСТЬ / ПРОСАДКА</p>
                </div>
              </div>
              <div className="text-right hidden md:block">
                <div className="text-3xl font-black text-teal-400">CAGR/DD</div>
                <div className="text-[10px] opacity-50">базовая формула</div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Ловушка «высокой доходности»</div>
                  <p className="text-sm opacity-80">
                    Трейдер хвастается +100% годовых, но умалчивает о просадке -60%. 
                    <span className="text-foreground font-medium"> Такая система разрушает капитал и нервы. Вам нужна не просто доходность, а КАЧЕСТВЕННАЯ доходность.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is it */}
            <div className="mb-8">
              <h3 className="text-foreground font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-teal-400" size={18} />
                Что такое Calmar Ratio?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-teal-400">Calmar Ratio</strong> — это коэффициент, показывающий, 
                сколько годовой доходности вы получаете на каждый процент максимальной просадки.
                <span className="italic text-foreground"> Название происходит от California Managed Account Reports.</span>
              </p>
              <p className="text-sm opacity-80 leading-relaxed">
                Это любимый показатель <strong className="text-foreground">хедж-фондов</strong> и профессиональных управляющих, 
                потому что он чётко отвечает на вопрос: <strong className="text-teal-400">«Стоит ли эта доходность тех просадок, которые приходится терпеть?»</strong>
              </p>
            </div>

            {/* Analogy */}
            <div className="mb-8">
              <h3 className="text-foreground font-bold text-lg mb-3 flex items-center gap-2">
                <Flame className="text-orange-400" size={18} />
                Аналогия: Американские горки vs Скоростной поезд
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Представьте два способа добраться из Москвы в Питер:
              </p>
              <div className="grid md:grid-cols-2 gap-4 mb-4">
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20">
                  <div className="text-red-400 font-black text-xl text-center mb-2">🎢 Американские горки</div>
                  <div className="text-sm text-center opacity-80 mb-2">+100% доход, -60% просадка</div>
                  <div className="text-center">
                    <span className="text-red-400 font-bold text-2xl">Calmar = 1.67</span>
                  </div>
                  <div className="text-xs opacity-60 text-center mt-2">
                    Вы доедете, но будете измотаны и седы
                  </div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20">
                  <div className="text-green-400 font-black text-xl text-center mb-2">🚄 Скоростной поезд</div>
                  <div className="text-sm text-center opacity-80 mb-2">+40% доход, -10% просадка</div>
                  <div className="text-center">
                    <span className="text-green-400 font-bold text-2xl">Calmar = 4.0 ✓</span>
                  </div>
                  <div className="text-xs opacity-60 text-center mt-2">
                    Меньше доход, но качество поездки в разы лучше
                  </div>
                </div>
              </div>
              <p className="text-xs opacity-50 text-center italic">
                Высокий Calmar = комфортная и устойчивая торговля
              </p>
            </div>

            {/* Formula */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-foreground font-bold text-lg mb-4 flex items-center gap-2">
                📐 Формула
              </h3>
              <div className="bg-teal-500/10 p-4 rounded-lg font-mono text-center mb-4">
                <span className="text-teal-400 text-lg">Calmar Ratio = CAGR / Max Drawdown</span>
              </div>
              <div className="grid md:grid-cols-2 gap-4 text-sm">
                <div className="text-center">
                  <div className="text-teal-400 font-bold">CAGR</div>
                  <div className="opacity-60">Compound Annual Growth Rate</div>
                  <div className="text-xs opacity-40">Среднегодовая доходность с учётом реинвестирования</div>
                </div>
                <div className="text-center">
                  <div className="text-teal-400 font-bold">Max Drawdown</div>
                  <div className="opacity-60">Максимальная просадка</div>
                  <div className="text-xs opacity-40">Крупнейшее падение от пика до впадины</div>
                </div>
              </div>
              <div className="mt-4 p-3 bg-teal-500/5 rounded text-sm text-center">
                <strong>Пример:</strong> CAGR = 30%, Max DD = 15% → Calmar = 30/15 = <span className="text-teal-400 font-bold">2.0</span>
              </div>
            </div>

            {/* Interpretation */}
            <div className="mb-8">
              <h3 className="text-foreground font-bold text-lg mb-4 flex items-center gap-2">
                📊 Интерпретация значений
              </h3>
              <div className="grid md:grid-cols-5 gap-2 text-center text-sm">
                <div className="bg-red-500/20 p-3 rounded-lg">
                  <div className="text-red-400 font-bold text-xl">&lt; 0</div>
                  <div className="text-xs mt-1 opacity-80">Убыточная система</div>
                </div>
                <div className="bg-orange-500/20 p-3 rounded-lg">
                  <div className="text-orange-400 font-bold text-xl">0 - 0.5</div>
                  <div className="text-xs mt-1 opacity-80">Плохо</div>
                </div>
                <div className="bg-yellow-500/20 p-3 rounded-lg">
                  <div className="text-yellow-400 font-bold text-xl">0.5 - 1.0</div>
                  <div className="text-xs mt-1 opacity-80">Удовл.</div>
                </div>
                <div className="bg-green-500/20 p-3 rounded-lg">
                  <div className="text-green-400 font-bold text-xl">1.0 - 3.0</div>
                  <div className="text-xs mt-1 opacity-80">Хорошо ✓</div>
                </div>
                <div className="bg-teal-500/20 p-3 rounded-lg">
                  <div className="text-teal-400 font-bold text-xl">&gt; 3.0</div>
                  <div className="text-xs mt-1 opacity-80">Топ фонды 🏆</div>
                </div>
              </div>
            </div>

            {/* Real world examples */}
            <div className="mb-8">
              <h3 className="text-foreground font-bold text-lg mb-4 flex items-center gap-2">
                🌍 Примеры из реального мира
              </h3>
              <div className="space-y-3">
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">📈</span>
                    <div>
                      <div className="font-bold">S&P 500 (долгосрок)</div>
                      <div className="text-xs opacity-60">Индексное инвестирование</div>
                    </div>
                  </div>
                  <div className="text-yellow-400 font-bold">~0.5-0.7</div>
                </div>
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">🏦</span>
                    <div>
                      <div className="font-bold">Хороший хедж-фонд</div>
                      <div className="text-xs opacity-60">Профессиональное управление</div>
                    </div>
                  </div>
                  <div className="text-green-400 font-bold">1.5-2.5</div>
                </div>
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">🥇</span>
                    <div>
                      <div className="font-bold">Топ CTA/Quant фонды</div>
                      <div className="text-xs opacity-60">Элитные алгоритмы</div>
                    </div>
                  </div>
                  <div className="text-teal-400 font-bold">3.0+</div>
                </div>
                <div className="flex items-center justify-between p-3 bg-white/5 rounded-lg">
                  <div className="flex items-center gap-3">
                    <span className="text-2xl">🎰</span>
                    <div>
                      <div className="font-bold">Типичный ритейл-трейдер</div>
                      <div className="text-xs opacity-60">Без системы</div>
                    </div>
                  </div>
                  <div className="text-red-400 font-bold">&lt; 0</div>
                </div>
              </div>
            </div>

            {/* Comparison with other ratios */}
            <div className="mb-8">
              <h3 className="text-foreground font-bold text-lg mb-4 flex items-center gap-2">
                ⚖️ Сравнение с другими коэффициентами
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left py-2 px-3">Коэффициент</th>
                      <th className="text-left py-2 px-3">Числитель</th>
                      <th className="text-left py-2 px-3">Знаменатель</th>
                      <th className="text-left py-2 px-3">Фокус</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-white/5">
                      <td className="py-2 px-3 font-bold text-teal-400">Calmar</td>
                      <td className="py-2 px-3">CAGR</td>
                      <td className="py-2 px-3">Max Drawdown</td>
                      <td className="py-2 px-3">Экстремальные потери</td>
                    </tr>
                    <tr className="border-b border-white/5">
                      <td className="py-2 px-3 font-bold text-blue-400">Sharpe</td>
                      <td className="py-2 px-3">Return - Rf</td>
                      <td className="py-2 px-3">Volatility (σ)</td>
                      <td className="py-2 px-3">Общая волатильность</td>
                    </tr>
                    <tr className="border-b border-white/5">
                      <td className="py-2 px-3 font-bold text-purple-400">Sortino</td>
                      <td className="py-2 px-3">Return - Rf</td>
                      <td className="py-2 px-3">Downside Dev</td>
                      <td className="py-2 px-3">Нисходящий риск</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 font-bold text-green-400">Recovery</td>
                      <td className="py-2 px-3">Total Return</td>
                      <td className="py-2 px-3">Max Drawdown</td>
                      <td className="py-2 px-3">Скорость восстановления</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* How to improve */}
            <div className="mb-8">
              <h3 className="text-foreground font-bold text-lg mb-4 flex items-center gap-2">
                🚀 Как улучшить Calmar Ratio?
              </h3>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20">
                  <div className="font-bold text-green-400 mb-2">✅ Увеличить CAGR</div>
                  <ul className="text-sm space-y-1 opacity-80">
                    <li>• Улучшить качество входов (MAE анализ)</li>
                    <li>• Оптимизировать выходы (MFE анализ)</li>
                    <li>• Использовать Optimal f для размера позиций</li>
                  </ul>
                </div>
                <div className="bg-teal-500/10 p-4 rounded-lg border border-teal-500/20">
                  <div className="font-bold text-teal-400 mb-2">🛡️ Уменьшить Max DD</div>
                  <ul className="text-sm space-y-1 opacity-80">
                    <li>• Жёсткие стоп-лоссы</li>
                    <li>• Диверсификация по инструментам</li>
                    <li>• Снижение риска после серии убытков</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Pro Tip */}
            <div className="bg-gradient-to-r from-teal-500/20 to-green-500/20 p-4 rounded-lg border border-teal-500/30">
              <h4 className="font-bold text-teal-400 mb-2 flex items-center gap-2">
                <Crown size={16} />
                Инсайт от хедж-фондов
              </h4>
              <ul className="text-sm space-y-1 opacity-80">
                <li>📊 Calmar &gt; 2.0 позволяет привлекать институциональные деньги</li>
                <li>🎯 Топ-фонды оптимизируют под Calmar, а не под абсолютную доходность</li>
                <li>⚡ Eqio автоматически рассчитывает CAGR с учётом периода торговли</li>
              </ul>
            </div>
          </div>
        </section>

        {/* MAE/MFE */}
        <section id="mae-mfe" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-yellow-500/15 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-yellow-500 to-yellow-700 rounded-xl shadow-lg shadow-yellow-500/20">
                  <Target size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">MAE / MFE</h2>
                    <span className="px-2 py-0.5 bg-yellow-500/20 rounded text-[10px] font-mono text-yellow-400">ОПТИМИЗАЦИЯ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">MAXIMUM ADVERSE / FAVORABLE EXCURSION</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Деньги на столе</div>
                  <p className="text-sm opacity-80">
                    Вы ставите стоп-лосс на глаз. Вы забираете прибыль, когда «кажется достаточно». 
                    <span className="text-white font-medium"> А что, если данные покажут, где РЕАЛЬНО нужно ставить стоп и тейк?</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is MAE/MFE */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-yellow-400" size={18} />
                Что такое MAE и MFE?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Эти метрики анализируют <strong className="text-white">внутреннюю динамику</strong> каждой сделки, 
                показывая, насколько далеко цена уходила против вас (MAE) и в вашу пользу (MFE).
              </p>
            </div>

            {/* MAE & MFE Detailed */}
            <div className="grid md:grid-cols-2 gap-6 mb-8">
              {/* MAE */}
              <div className="bg-gradient-to-br from-red-500/10 to-red-500/5 p-6 rounded-xl border border-red-500/20">
                <h3 className="font-bold text-red-400 text-lg mb-3 flex items-center gap-2">
                  <TrendingDown size={18} />
                  MAE (Maximum Adverse Excursion)
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  Максимальный уход цены <strong className="text-white">против вашей позиции</strong> во время сделки. 
                  Показывает, сколько «боли» вы терпели.
                </p>
                
                <div className="bg-black/30 p-4 rounded-lg mb-4">
                  <div className="text-xs font-mono text-red-400 mb-2">📉 Пример:</div>
                  <p className="text-sm opacity-80 mb-2">
                    Вы купили акцию по 100₽. Стоп-лосс = 90₽ (риск 10₽).
                  </p>
                  <p className="text-sm opacity-80 mb-2">
                    Цена упала до 95₽, потом выросла до 120₽, вы закрыли с прибылью.
                  </p>
                  <p className="text-sm">
                    <span className="text-red-400 font-bold">MAE = −5₽</span> — максимальный уход против вас.
                  </p>
                </div>

                <div className="bg-red-500/20 p-3 rounded border border-red-500/30">
                  <div className="font-bold text-white text-sm mb-1">💡 Инсайт:</div>
                  <p className="text-xs opacity-80">
                    Если в 95% прибыльных сделок MAE &lt; 5₽, а ваш стоп = 10₽ — 
                    <strong className="text-white"> вы можете уменьшить стоп вдвое</strong> и удвоить размер позиции!
                  </p>
                </div>
              </div>

              {/* MFE */}
              <div className="bg-gradient-to-br from-green-500/10 to-green-500/5 p-6 rounded-xl border border-green-500/20">
                <h3 className="font-bold text-green-400 text-lg mb-3 flex items-center gap-2">
                  <TrendingUp size={18} />
                  MFE (Maximum Favorable Excursion)
                </h3>
                <p className="text-sm opacity-70 mb-4">
                  Максимальный уход цены <strong className="text-white">в вашу пользу</strong> во время сделки. 
                  Показывает, сколько «бумажной» прибыли вы видели.
                </p>
                
                <div className="bg-black/30 p-4 rounded-lg mb-4">
                  <div className="text-xs font-mono text-green-400 mb-2">📈 Пример:</div>
                  <p className="text-sm opacity-80 mb-2">
                    Вы купили по 100₽. Цена выросла до 130₽, потом упала.
                  </p>
                  <p className="text-sm opacity-80 mb-2">
                    Вы закрыли по 115₽ с прибылью +15₽.
                  </p>
                  <p className="text-sm">
                    <span className="text-green-400 font-bold">MFE = +30₽</span> — вы оставили 15₽ на столе!
                  </p>
                </div>

                <div className="bg-green-500/20 p-3 rounded border border-green-500/30">
                  <div className="font-bold text-white text-sm mb-1">💡 Инсайт:</div>
                  <p className="text-xs opacity-80">
                    Если средний MFE = 30₽, а средняя прибыль = 15₽ — 
                    <strong className="text-white"> вы систематически выходите слишком рано</strong>. Попробуйте трейлинг-стоп!
                  </p>
                </div>
              </div>
            </div>

            {/* How to use */}
            <div className="bg-gradient-to-r from-yellow-500/10 via-accent/10 to-yellow-500/10 rounded-xl p-6 mb-8 border border-yellow-500/20">
              <h3 className="text-white font-bold text-lg mb-4">🔧 Как использовать MAE/MFE для оптимизации</h3>
              
              <div className="space-y-4">
                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="font-bold text-yellow-400 mb-2">1. Оптимизация стоп-лосса (MAE)</div>
                  <ul className="text-sm opacity-80 space-y-1">
                    <li>• Постройте распределение MAE для прибыльных сделок</li>
                    <li>• Найдите точку, где отсекается 90-95% сделок</li>
                    <li>• Это ваш <strong className="text-white">оптимальный стоп-лосс</strong></li>
                  </ul>
                </div>
                
                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="font-bold text-yellow-400 mb-2">2. Оптимизация тейк-профита (MFE)</div>
                  <ul className="text-sm opacity-80 space-y-1">
                    <li>• Постройте распределение MFE</li>
                    <li>• Найдите среднее и медиану</li>
                    <li>• Ставьте тейк на уровне 70-80% от среднего MFE</li>
                  </ul>
                </div>

                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="font-bold text-yellow-400 mb-2">3. Трейлинг-стоп (MFE − MAE)</div>
                  <ul className="text-sm opacity-80 space-y-1">
                    <li>• Анализируйте, насколько цена откатывает от MFE</li>
                    <li>• Настройте трейлинг-стоп на этот откат</li>
                    <li>• Захватывайте больше движения!</li>
                  </ul>
                </div>
              </div>
            </div>

            {/* Real example */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4">📊 Реальный пример оптимизации</h3>
              
              <div className="grid md:grid-cols-2 gap-6">
                <div>
                  <div className="text-xs font-mono uppercase tracking-widest opacity-50 mb-3">До оптимизации</div>
                  <div className="space-y-2">
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Стоп-лосс:</span>
                      <span className="text-red-400">−100₽ (2%)</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Средняя MAE в прибыльных:</span>
                      <span className="text-yellow-400">−25₽</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Размер позиции:</span>
                      <span>10 акций</span>
                    </div>
                  </div>
                </div>
                <div>
                  <div className="text-xs font-mono uppercase tracking-widest opacity-50 mb-3">После оптимизации</div>
                  <div className="space-y-2">
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Стоп-лосс:</span>
                      <span className="text-green-400">−35₽ (тот же риск)</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Буфер:</span>
                      <span className="text-green-400">+10₽ над MAE</span>
                    </div>
                    <div className="flex justify-between p-2 bg-black/30 rounded">
                      <span className="opacity-70">Размер позиции:</span>
                      <span className="text-green-400 font-bold">28 акций (+180%!)</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="mt-4 p-3 bg-accent/10 rounded border border-accent/20 text-center">
                <span className="text-accent font-bold">Результат:</span>
                <span className="text-sm opacity-80 ml-2">Тот же риск в ₽, но прибыль почти в 3 раза больше!</span>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-yellow-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-yellow-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-yellow-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Анализируйте MAE/MFE отдельно для лонгов и шортов — они могут отличаться</li>
                <li>📊 Минимум 30 сделок для надёжного анализа</li>
                <li>⚠️ MAE &gt; стоп-лосса = сделка была обречена. Фильтруйте такие сетапы!</li>
                <li>🎯 Eqio строит графики MAE/MFE автоматически</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Monte Carlo Simulation */}
        <section id="monte-carlo" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute top-0 right-0 w-80 h-80 bg-indigo-500/15 rounded-full blur-3xl" />
          <div className="absolute bottom-0 left-0 w-60 h-60 bg-violet-500/10 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-indigo-500 to-violet-700 rounded-xl shadow-lg shadow-indigo-500/20">
                  <Dice5 size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Monte Carlo</h2>
                    <span className="px-2 py-0.5 bg-indigo-500/20 rounded text-[10px] font-mono text-indigo-400">СИМУЛЯЦИЯ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">10,000 ПАРАЛЛЕЛЬНЫХ ВСЕЛЕННЫХ</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Ложная уверенность</div>
                  <p className="text-sm opacity-80">
                    У вас 100 прибыльных сделок и вы думаете, что система работает. Но что, если вам просто повезло? 
                    <span className="text-white font-medium"> Что, если при другом раскладе вы бы потеряли 50% депозита?</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is Monte Carlo */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <Dice5 className="text-indigo-400" size={18} />
                Что такое Monte Carlo симуляция?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Monte Carlo берёт ваши реальные сделки и <strong className="text-white">перемешивает их 10,000 раз</strong> 
                в случайном порядке. Каждая перестановка — это альтернативная вселенная, где вы совершили 
                те же сделки, но в другой последовательности.
              </p>
              <div className="bg-indigo-500/10 p-4 rounded-lg border border-indigo-500/20">
                <p className="text-sm italic text-center">
                  «Вы видели только ОДНУ реализацию своей стратегии. Monte Carlo показывает 
                  <span className="text-indigo-400 font-bold"> ВСЕ возможные исходы</span>.»
                </p>
              </div>
            </div>

            {/* Visual Example */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Визуальный пример</h3>
              <div className="bg-black/40 rounded-xl p-6 border border-white/10">
                <div className="text-xs font-mono opacity-50 mb-4 text-center">10,000 СИМУЛЯЦИЙ КРИВОЙ КАПИТАЛА</div>
                
                {/* Simulated equity curves */}
                <div className="relative h-40 mb-4">
                  {/* Background lines - multiple paths */}
                  <div className="absolute inset-0 flex items-end">
                    <div className="w-full h-full relative">
                      {/* Worst case */}
                      <div className="absolute bottom-0 left-0 w-full h-[20%] bg-gradient-to-t from-red-500/10 to-transparent" />
                      {/* Best case */}
                      <div className="absolute top-0 left-0 w-full h-[30%] bg-gradient-to-b from-green-500/10 to-transparent" />
                      {/* Middle band */}
                      <div className="absolute top-[35%] left-0 w-full h-[30%] bg-indigo-500/20" />
                      
                      {/* Your actual path */}
                      <svg className="absolute inset-0 w-full h-full">
                        <path 
                          d="M0,120 Q50,100 100,80 T200,60 T300,50 T400,30" 
                          fill="none" 
                          stroke="rgb(129, 140, 248)" 
                          strokeWidth="3"
                        />
                      </svg>
                    </div>
                  </div>
                </div>
                
                <div className="grid grid-cols-3 gap-4 text-center text-xs">
                  <div className="p-2 bg-red-500/10 rounded border border-red-500/20">
                    <div className="text-red-400 font-bold">5% худших</div>
                    <div className="opacity-60">−35% депозита</div>
                  </div>
                  <div className="p-2 bg-indigo-500/20 rounded border border-indigo-500/30">
                    <div className="text-indigo-400 font-bold">Медиана (50%)</div>
                    <div className="opacity-60">+45% депозита</div>
                  </div>
                  <div className="p-2 bg-green-500/10 rounded border border-green-500/20">
                    <div className="text-green-400 font-bold">5% лучших</div>
                    <div className="opacity-60">+120% депозита</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Key Insights */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">💎 Что даёт Monte Carlo?</h3>
              <div className="grid md:grid-cols-2 gap-4">
                <div className="bg-gradient-to-br from-indigo-500/10 to-indigo-500/5 p-5 rounded-xl border border-indigo-500/20">
                  <div className="text-indigo-400 font-bold text-lg mb-2">1. Реальные границы просадки</div>
                  <p className="text-sm opacity-70 mb-3">
                    Ваша историческая просадка −15%. Но Monte Carlo показывает, что в 5% случаев просадка достигла бы −40%!
                  </p>
                  <div className="bg-black/30 p-3 rounded text-xs">
                    <span className="text-red-400">→</span> Ваш стоп-лосс депозита должен быть минимум −45%
                  </div>
                </div>
                
                <div className="bg-gradient-to-br from-violet-500/10 to-violet-500/5 p-5 rounded-xl border border-violet-500/20">
                  <div className="text-violet-400 font-bold text-lg mb-2">2. Вероятность достижения целей</div>
                  <p className="text-sm opacity-70 mb-3">
                    Какова вероятность удвоить депозит за год? Monte Carlo покажет точный процент!
                  </p>
                  <div className="bg-black/30 p-3 rounded text-xs">
                    <span className="text-green-400">→</span> Удвоить депозит: 73% | Утроить: 31%
                  </div>
                </div>
                
                <div className="bg-gradient-to-br from-blue-500/10 to-blue-500/5 p-5 rounded-xl border border-blue-500/20">
                  <div className="text-blue-400 font-bold text-lg mb-2">3. Stress-тест размера позиции</div>
                  <p className="text-sm opacity-70 mb-3">
                    Что будет, если увеличить риск с 1% до 2%? Monte Carlo покажет последствия!
                  </p>
                  <div className="bg-black/30 p-3 rounded text-xs">
                    <span className="text-yellow-400">→</span> Прибыль ×2, но риск руина ×4
                  </div>
                </div>
                
                <div className="bg-gradient-to-br from-cyan-500/10 to-cyan-500/5 p-5 rounded-xl border border-cyan-500/20">
                  <div className="text-cyan-400 font-bold text-lg mb-2">4. Валидация стратегии</div>
                  <p className="text-sm opacity-70 mb-3">
                    Если даже в 95% симуляций вы в плюсе — стратегия робастная!
                  </p>
                  <div className="bg-black/30 p-3 rounded text-xs">
                    <span className="text-green-400">→</span> 95% уверенности = статистическая значимость
                  </div>
                </div>
              </div>
            </div>

            {/* Confidence Intervals */}
            <div className="bg-gradient-to-r from-indigo-500/10 via-violet-500/10 to-indigo-500/10 rounded-xl p-6 mb-8 border border-indigo-500/20">
              <h3 className="text-white font-bold text-lg mb-4">📐 Доверительные интервалы</h3>
              <p className="text-sm opacity-80 mb-4">
                Monte Carlo показывает не одно число, а <strong className="text-white">диапазон возможных результатов</strong>:
              </p>
              
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div className="w-24 text-right text-xs font-mono text-red-400">Худший 5%</div>
                  <div className="flex-1 h-6 bg-black/30 rounded relative overflow-hidden">
                    <div className="absolute left-0 top-0 h-full w-[15%] bg-red-500/50" />
                  </div>
                  <div className="w-20 text-xs opacity-60">−35%</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-24 text-right text-xs font-mono text-yellow-400">25 перцентиль</div>
                  <div className="flex-1 h-6 bg-black/30 rounded relative overflow-hidden">
                    <div className="absolute left-0 top-0 h-full w-[35%] bg-yellow-500/50" />
                  </div>
                  <div className="w-20 text-xs opacity-60">+15%</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-24 text-right text-xs font-mono text-indigo-400">Медиана</div>
                  <div className="flex-1 h-6 bg-black/30 rounded relative overflow-hidden">
                    <div className="absolute left-0 top-0 h-full w-[55%] bg-indigo-500/50" />
                  </div>
                  <div className="w-20 text-xs opacity-60">+45%</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-24 text-right text-xs font-mono text-blue-400">75 перцентиль</div>
                  <div className="flex-1 h-6 bg-black/30 rounded relative overflow-hidden">
                    <div className="absolute left-0 top-0 h-full w-[75%] bg-blue-500/50" />
                  </div>
                  <div className="w-20 text-xs opacity-60">+85%</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-24 text-right text-xs font-mono text-green-400">Лучший 5%</div>
                  <div className="flex-1 h-6 bg-black/30 rounded relative overflow-hidden">
                    <div className="absolute left-0 top-0 h-full w-[95%] bg-green-500/50" />
                  </div>
                  <div className="w-20 text-xs opacity-60">+120%</div>
                </div>
              </div>
              
              <div className="mt-4 p-3 bg-indigo-500/10 rounded border border-indigo-500/20 text-center text-sm">
                💡 Реалистичное ожидание: <strong className="text-white">от +15% до +85%</strong> (50% интервал)
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-indigo-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-indigo-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-indigo-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Минимум <strong className="text-white">50 сделок</strong> для надёжной симуляции</li>
                <li>📊 Используйте 95-й перцентиль просадки для расчёта максимального риска</li>
                <li>⚠️ Если в 10%+ симуляций вы теряете &gt;50% — уменьшите размер позиции!</li>
                <li>🎯 Eqio запускает 10,000 симуляций за секунды</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Risk of Ruin */}
        <section id="risk-of-ruin" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 -right-20 w-80 h-80 bg-rose-500/15 rounded-full blur-3xl" />
          <div className="absolute -bottom-20 -left-20 w-60 h-60 bg-red-500/10 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-rose-500 to-red-700 rounded-xl shadow-lg shadow-rose-500/20">
                  <Skull size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Risk of Ruin</h2>
                    <span className="px-2 py-0.5 bg-rose-500/20 rounded text-[10px] font-mono text-rose-400">ВЫЖИВАНИЕ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">ВЕРОЯТНОСТЬ ПОЛНОГО УНИЧТОЖЕНИЯ</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <Skull size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Главный вопрос трейдинга</div>
                  <p className="text-sm opacity-80">
                    «Какова вероятность, что я потеряю ВСЁ?» Большинство трейдеров избегают этого вопроса. 
                    <span className="text-white font-medium"> Eqio даёт честный ответ в процентах.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is Risk of Ruin */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <Skull className="text-rose-400" size={18} />
                Что такое Risk of Ruin?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-rose-400">Risk of Ruin (RoR)</strong> — это вероятность потерять заданный 
                процент капитала (обычно 50% или 100%) при текущей стратегии и размере позиции.
              </p>
              <div className="bg-rose-500/10 p-4 rounded-lg border border-rose-500/20">
                <p className="text-sm italic text-center">
                  «Не важно, насколько прибыльна ваша стратегия, если риск руина &gt;5% — 
                  <span className="text-rose-400 font-bold"> вы играете в русскую рулетку.</span>»
                </p>
              </div>
            </div>

            {/* The Math */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                📐 Формула Risk of Ruin
              </h3>
              <div className="bg-rose-500/10 p-4 rounded-lg font-mono text-center mb-4">
                <span className="text-rose-400 text-lg">RoR = ((1 − Edge) / (1 + Edge))^N</span>
              </div>
              <div className="grid md:grid-cols-3 gap-4 text-sm mb-4">
                <div className="text-center">
                  <div className="text-rose-400 font-bold">Edge</div>
                  <div className="opacity-60 text-xs">Преимущество (WinRate × AvgWin − LossRate × AvgLoss)</div>
                </div>
                <div className="text-center">
                  <div className="text-rose-400 font-bold">N</div>
                  <div className="opacity-60 text-xs">Количество единиц риска до руина</div>
                </div>
                <div className="text-center">
                  <div className="text-rose-400 font-bold">RoR</div>
                  <div className="opacity-60 text-xs">Вероятность руина (0−1)</div>
                </div>
              </div>
              <p className="text-xs opacity-50 text-center italic">
                * Eqio рассчитывает это через Monte Carlo для большей точности
              </p>
            </div>

            {/* Risk of Ruin Table */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Таблица Risk of Ruin</h3>
              <p className="text-sm opacity-70 mb-4">
                Как размер позиции влияет на вероятность потерять 50% депозита:
              </p>
              
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left p-3 opacity-50 font-mono text-xs">Риск на сделку</th>
                      <th className="text-center p-3 opacity-50 font-mono text-xs">Win Rate 40%</th>
                      <th className="text-center p-3 opacity-50 font-mono text-xs">Win Rate 50%</th>
                      <th className="text-center p-3 opacity-50 font-mono text-xs">Win Rate 60%</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-green-400">1%</td>
                      <td className="p-3 text-center text-green-400">0.1%</td>
                      <td className="p-3 text-center text-green-400">&lt;0.01%</td>
                      <td className="p-3 text-center text-green-400">&lt;0.01%</td>
                    </tr>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-yellow-400">2%</td>
                      <td className="p-3 text-center text-yellow-400">2.3%</td>
                      <td className="p-3 text-center text-green-400">0.5%</td>
                      <td className="p-3 text-center text-green-400">0.1%</td>
                    </tr>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-orange-400">5%</td>
                      <td className="p-3 text-center text-red-400">18%</td>
                      <td className="p-3 text-center text-yellow-400">7%</td>
                      <td className="p-3 text-center text-yellow-400">3%</td>
                    </tr>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-red-400">10%</td>
                      <td className="p-3 text-center text-red-400 font-bold">45%</td>
                      <td className="p-3 text-center text-red-400">28%</td>
                      <td className="p-3 text-center text-orange-400">15%</td>
                    </tr>
                    <tr className="hover:bg-white/5">
                      <td className="p-3 font-mono text-red-500">20%</td>
                      <td className="p-3 text-center text-red-500 font-bold">78%</td>
                      <td className="p-3 text-center text-red-400 font-bold">62%</td>
                      <td className="p-3 text-center text-red-400">41%</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              
              <div className="mt-4 p-3 bg-red-500/10 rounded border border-red-500/20 text-center text-sm">
                ⚠️ Даже с 60% Win Rate, риск 10% на сделку = <strong className="text-red-400">15% шанс потерять половину!</strong>
              </div>
            </div>

            {/* Visual Comparison */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">⚔️ Два трейдера, одна стратегия</h3>
              <div className="grid md:grid-cols-2 gap-6">
                <div className="bg-gradient-to-br from-green-500/10 to-green-500/5 p-6 rounded-xl border border-green-500/20">
                  <div className="flex items-center gap-2 mb-4">
                    <Shield size={24} className="text-green-400" />
                    <span className="font-bold text-green-400 text-lg">Консервативный</span>
                  </div>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Риск на сделку:</span>
                      <span className="text-green-400 font-bold">1%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Risk of Ruin:</span>
                      <span className="text-green-400 font-bold">0.1%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Годовая доходность:</span>
                      <span className="text-white">+25%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Макс. просадка:</span>
                      <span className="text-green-400">−12%</span>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-green-500/20 rounded text-center">
                    <span className="text-green-400 font-bold">😴 Спит спокойно</span>
                  </div>
                </div>
                
                <div className="bg-gradient-to-br from-red-500/10 to-red-500/5 p-6 rounded-xl border border-red-500/20">
                  <div className="flex items-center gap-2 mb-4">
                    <Flame size={24} className="text-red-400" />
                    <span className="font-bold text-red-400 text-lg">Агрессивный</span>
                  </div>
                  <div className="space-y-3 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Риск на сделку:</span>
                      <span className="text-red-400 font-bold">10%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Risk of Ruin:</span>
                      <span className="text-red-400 font-bold">28%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Годовая доходность:</span>
                      <span className="text-white">+120%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Макс. просадка:</span>
                      <span className="text-red-400">−65%</span>
                    </div>
                  </div>
                  <div className="mt-4 p-3 bg-red-500/20 rounded text-center">
                    <span className="text-red-400 font-bold">💀 1 из 4 сольётся</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Safe Zone */}
            <div className="bg-gradient-to-r from-green-500/10 via-yellow-500/10 to-red-500/10 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4">🛡️ Безопасные зоны Risk of Ruin</h3>
              
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div className="w-20 text-right">
                    <span className="text-green-400 font-bold">&lt;1%</span>
                  </div>
                  <div className="flex-1 h-8 bg-green-500/30 rounded flex items-center px-3">
                    <span className="text-xs font-bold text-green-400">ПРОФЕССИОНАЛ</span>
                  </div>
                  <div className="w-48 text-xs opacity-60">Институциональный уровень</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-20 text-right">
                    <span className="text-green-400 font-bold">1−5%</span>
                  </div>
                  <div className="flex-1 h-8 bg-green-500/20 rounded flex items-center px-3">
                    <span className="text-xs font-bold text-green-400">БЕЗОПАСНО</span>
                  </div>
                  <div className="w-48 text-xs opacity-60">Рекомендуемый диапазон</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-20 text-right">
                    <span className="text-yellow-400 font-bold">5−15%</span>
                  </div>
                  <div className="flex-1 h-8 bg-yellow-500/20 rounded flex items-center px-3">
                    <span className="text-xs font-bold text-yellow-400">РИСКОВАННО</span>
                  </div>
                  <div className="w-48 text-xs opacity-60">Только для опытных</div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="w-20 text-right">
                    <span className="text-red-400 font-bold">&gt;15%</span>
                  </div>
                  <div className="flex-1 h-8 bg-red-500/30 rounded flex items-center px-3">
                    <span className="text-xs font-bold text-red-400">ОПАСНО</span>
                  </div>
                  <div className="w-48 text-xs opacity-60">Азартная игра, не трейдинг</div>
                </div>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-rose-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-rose-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-rose-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Держите Risk of Ruin <strong className="text-white">&lt;5%</strong> — это золотой стандарт</li>
                <li>📊 Если RoR &gt;10% — уменьшайте размер позиции, пока не станет безопасно</li>
                <li>⚠️ Высокий Win Rate НЕ защищает от руина при большом риске</li>
                <li>🎯 Eqio рассчитывает RoR автоматически через Monte Carlo</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Time Patterns */}
        <section id="time-patterns" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute top-0 left-0 w-80 h-80 bg-sky-500/15 rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-0 w-60 h-60 bg-teal-500/10 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-sky-500 to-teal-600 rounded-xl shadow-lg shadow-sky-500/20">
                  <Clock size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Time Patterns</h2>
                    <span className="px-2 py-0.5 bg-sky-500/20 rounded text-[10px] font-mono text-sky-400">ХРОНОМЕТР</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">КОГДА ВАМ ТОРГОВАТЬ • КОГДА НЕ ТОРГОВАТЬ</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <Clock size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Слив в определённые часы</div>
                  <p className="text-sm opacity-80">
                    Вы сливаете после 19:00? По понедельникам? На американской сессии? 
                    <span className="text-white font-medium"> Если не знаете — вы теряете деньги вслепую.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is Time Analysis */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <Clock className="text-sky-400" size={18} />
                Зачем анализировать время?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Ваша торговля — это не просто числа. Это <strong className="text-white">вы в определённое время</strong>. 
                Утром вы свежий, вечером уставший. Понедельник — стресс после выходных, пятница — торопитесь закрыть всё.
              </p>
              <div className="bg-sky-500/10 p-4 rounded-lg border border-sky-500/20">
                <p className="text-sm italic text-center">
                  «Рынок работает 24/5, но <span className="text-sky-400 font-bold">вы — нет</span>. 
                  Найдите своё золотое окно.»
                </p>
              </div>
            </div>

            {/* Time of Day Analysis */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                <BarChart3 className="text-sky-400" size={18} />
                Анализ по времени суток
              </h3>
              
              <div className="bg-black/40 rounded-xl p-6 border border-white/10">
                <div className="text-xs font-mono opacity-50 mb-4 text-center">P&L ПО ЧАСАМ (ПРИМЕР)</div>
                
                {/* Hour bars */}
                <div className="flex items-end justify-between h-32 gap-1 mb-4">
                  {/* Morning */}
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-green-500/60 rounded-t" style={{height: '40%'}} />
                    <span className="text-[10px] opacity-50">9</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-green-500/80 rounded-t" style={{height: '70%'}} />
                    <span className="text-[10px] opacity-50">10</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-green-500 rounded-t" style={{height: '90%'}} />
                    <span className="text-[10px] text-green-400 font-bold">11</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-green-500/70 rounded-t" style={{height: '55%'}} />
                    <span className="text-[10px] opacity-50">12</span>
                  </div>
                  {/* Lunch */}
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-yellow-500/50 rounded-t" style={{height: '20%'}} />
                    <span className="text-[10px] opacity-50">13</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-red-500/40 rounded-t" style={{height: '15%'}} />
                    <span className="text-[10px] opacity-50">14</span>
                  </div>
                  {/* Afternoon */}
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-green-500/50 rounded-t" style={{height: '35%'}} />
                    <span className="text-[10px] opacity-50">15</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-green-500/40 rounded-t" style={{height: '25%'}} />
                    <span className="text-[10px] opacity-50">16</span>
                  </div>
                  {/* Evening */}
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-red-500/60 rounded-t" style={{height: '30%'}} />
                    <span className="text-[10px] opacity-50">17</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-red-500/80 rounded-t" style={{height: '50%'}} />
                    <span className="text-[10px] opacity-50">18</span>
                  </div>
                  <div className="flex-1 flex flex-col items-center gap-1">
                    <div className="w-full bg-red-500 rounded-t" style={{height: '75%'}} />
                    <span className="text-[10px] text-red-400 font-bold">19</span>
                  </div>
                </div>
                
                <div className="grid grid-cols-3 gap-4 text-center text-xs">
                  <div className="p-2 bg-green-500/10 rounded border border-green-500/20">
                    <div className="text-green-400 font-bold">Утро (9-12)</div>
                    <div className="opacity-60">+15,000₽</div>
                  </div>
                  <div className="p-2 bg-yellow-500/10 rounded border border-yellow-500/20">
                    <div className="text-yellow-400 font-bold">День (13-16)</div>
                    <div className="opacity-60">+2,000₽</div>
                  </div>
                  <div className="p-2 bg-red-500/10 rounded border border-red-500/20">
                    <div className="text-red-400 font-bold">Вечер (17-19)</div>
                    <div className="opacity-60">−8,000₽</div>
                  </div>
                </div>
              </div>
              
              <div className="mt-4 p-3 bg-sky-500/10 rounded border border-sky-500/20 text-center text-sm">
                💡 <strong className="text-white">Инсайт:</strong> Не торговать после 17:00 = +8,000₽ экономии!
              </div>
            </div>

            {/* Day of Week Analysis */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                <Calendar className="text-teal-400" size={18} />
                Анализ по дням недели
              </h3>
              
              <div className="grid grid-cols-5 gap-3">
                <div className="bg-yellow-500/10 p-4 rounded-lg border border-yellow-500/20 text-center">
                  <div className="text-yellow-400 font-bold text-lg mb-1">ПН</div>
                  <div className="text-xs opacity-50 mb-2">Понедельник</div>
                  <div className="text-yellow-400 font-mono text-sm">+2%</div>
                  <div className="text-[10px] opacity-40 mt-1">Осторожный старт</div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 text-center">
                  <div className="text-green-400 font-bold text-lg mb-1">ВТ</div>
                  <div className="text-xs opacity-50 mb-2">Вторник</div>
                  <div className="text-green-400 font-mono text-sm font-bold">+8%</div>
                  <div className="text-[10px] opacity-40 mt-1">Лучший день!</div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 text-center">
                  <div className="text-green-400 font-bold text-lg mb-1">СР</div>
                  <div className="text-xs opacity-50 mb-2">Среда</div>
                  <div className="text-green-400 font-mono text-sm">+5%</div>
                  <div className="text-[10px] opacity-40 mt-1">Стабильно</div>
                </div>
                <div className="bg-yellow-500/10 p-4 rounded-lg border border-yellow-500/20 text-center">
                  <div className="text-yellow-400 font-bold text-lg mb-1">ЧТ</div>
                  <div className="text-xs opacity-50 mb-2">Четверг</div>
                  <div className="text-yellow-400 font-mono text-sm">+1%</div>
                  <div className="text-[10px] opacity-40 mt-1">Нейтрально</div>
                </div>
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20 text-center">
                  <div className="text-red-400 font-bold text-lg mb-1">ПТ</div>
                  <div className="text-xs opacity-50 mb-2">Пятница</div>
                  <div className="text-red-400 font-mono text-sm font-bold">−6%</div>
                  <div className="text-[10px] opacity-40 mt-1">Не торговать!</div>
                </div>
              </div>
              
              <div className="mt-4 p-3 bg-red-500/10 rounded border border-red-500/20 text-center text-sm">
                ⚠️ Пятница = сливной день. <strong className="text-white">Уходить с рынка в 16:00!</strong>
              </div>
            </div>

            {/* Session Analysis */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">🌍 Анализ по сессиям</h3>
              <div className="grid md:grid-cols-3 gap-4">
                <div className="bg-gradient-to-br from-blue-500/10 to-blue-500/5 p-5 rounded-xl border border-blue-500/20">
                  <div className="text-blue-400 font-bold text-lg mb-2 flex items-center gap-2">
                    🇪🇺 Европа
                  </div>
                  <div className="text-xs opacity-50 mb-3">10:00 − 18:00 МСК</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Win Rate:</span>
                      <span className="text-green-400">58%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Profit Factor:</span>
                      <span className="text-green-400">1.8</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Сделок:</span>
                      <span>124</span>
                    </div>
                  </div>
                </div>
                
                <div className="bg-gradient-to-br from-green-500/10 to-green-500/5 p-5 rounded-xl border border-green-500/20">
                  <div className="text-green-400 font-bold text-lg mb-2 flex items-center gap-2">
                    🇺🇸 Америка
                  </div>
                  <div className="text-xs opacity-50 mb-3">16:30 − 23:00 МСК</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Win Rate:</span>
                      <span className="text-green-400">62%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Profit Factor:</span>
                      <span className="text-green-400 font-bold">2.1</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Сделок:</span>
                      <span>89</span>
                    </div>
                  </div>
                </div>
                
                <div className="bg-gradient-to-br from-red-500/10 to-red-500/5 p-5 rounded-xl border border-red-500/20">
                  <div className="text-red-400 font-bold text-lg mb-2 flex items-center gap-2">
                    🇯🇵 Азия
                  </div>
                  <div className="text-xs opacity-50 mb-3">03:00 − 10:00 МСК</div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Win Rate:</span>
                      <span className="text-yellow-400">45%</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Profit Factor:</span>
                      <span className="text-red-400">0.8</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Сделок:</span>
                      <span>31</span>
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="mt-4 p-3 bg-green-500/10 rounded border border-green-500/20 text-center text-sm">
                💡 Американская сессия = ваш <strong className="text-green-400">главный источник прибыли</strong>
              </div>
            </div>

            {/* Heatmap */}
            <div className="bg-gradient-to-r from-sky-500/10 via-teal-500/10 to-sky-500/10 rounded-xl p-6 mb-8 border border-sky-500/20">
              <h3 className="text-white font-bold text-lg mb-4">🔥 Тепловая карта (пример)</h3>
              <p className="text-sm opacity-70 mb-4">
                Eqio строит тепловую карту: день недели × час = P&L. Красные ячейки — убытки, зелёные — прибыль.
              </p>
              
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr>
                      <th className="p-2"></th>
                      <th className="p-2 text-center opacity-50">9</th>
                      <th className="p-2 text-center opacity-50">10</th>
                      <th className="p-2 text-center opacity-50">11</th>
                      <th className="p-2 text-center opacity-50">14</th>
                      <th className="p-2 text-center opacity-50">15</th>
                      <th className="p-2 text-center opacity-50">16</th>
                      <th className="p-2 text-center opacity-50">17</th>
                      <th className="p-2 text-center opacity-50">18</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td className="p-2 font-bold">ПН</td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/40 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/60 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-yellow-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/20 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/50 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/40 rounded" /></td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold text-green-400">ВТ</td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/60 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/80 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/50 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/40 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-yellow-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/20 rounded" /></td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold">СР</td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/50 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/70 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/60 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-yellow-500/20 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/20 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/40 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/50 rounded" /></td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold">ЧТ</td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/40 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-yellow-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-yellow-500/20 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/50 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/60 rounded" /></td>
                    </tr>
                    <tr>
                      <td className="p-2 font-bold text-red-400">ПТ</td>
                      <td className="p-1"><div className="w-full h-6 bg-yellow-500/30 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-green-500/20 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/20 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/40 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/60 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500/80 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500 rounded" /></td>
                      <td className="p-1"><div className="w-full h-6 bg-red-500 rounded" /></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              
              <div className="mt-4 text-center text-xs opacity-60">
                🟢 Зелёный = прибыль | 🟡 Жёлтый = нейтрально | 🔴 Красный = убыток
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-sky-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-sky-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-sky-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Торгуйте только в своё <strong className="text-white">«золотое окно»</strong> — часы с лучшей статистикой</li>
                <li>📊 Минимум 30 сделок на каждый временной слот для надёжного анализа</li>
                <li>⚠️ Если вечер убыточен — поставьте таймер и уходите с рынка!</li>
                <li>🎯 Eqio строит тепловые карты автоматически</li>
              </ul>
            </div>
          </div>
        </section>

        {/* R-Expectancy */}
        <section id="r-expectancy" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute top-0 left-0 w-80 h-80 bg-emerald-500/15 rounded-full blur-3xl" />
          <div className="absolute bottom-0 right-0 w-60 h-60 bg-green-500/10 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-emerald-500 to-green-600 rounded-xl shadow-lg shadow-emerald-500/20">
                  <DollarSign size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">R-Expectancy</h2>
                    <span className="px-2 py-0.5 bg-emerald-500/20 rounded text-[10px] font-mono text-emerald-400">ПРИБЫЛЬ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">МАТЕМАТИЧЕСКОЕ ОЖИДАНИЕ В ЕДИНИЦАХ РИСКА</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Рубли — это не всё</div>
                  <p className="text-sm opacity-80">
                    «Я заработал 50,000₽!» Но рисковали вы 100,000₽ или 10,000₽? 
                    <span className="text-white font-medium"> Без нормализации по риску сравнивать сделки бессмысленно.</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What is R */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <DollarSign className="text-emerald-400" size={18} />
                Что такое R?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                <strong className="text-emerald-400">R</strong> — это ваш <strong className="text-white">начальный риск</strong> в сделке. 
                Расстояние от входа до стоп-лосса. Все результаты измеряются в единицах R.
              </p>
              <div className="bg-emerald-500/10 p-4 rounded-lg border border-emerald-500/20">
                <p className="text-sm italic text-center">
                  «1R = ваш стоп-лосс. Заработали 3R = <span className="text-emerald-400 font-bold">прибыль в 3 раза больше риска</span>.»
                </p>
              </div>
            </div>

            {/* Formula */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4 flex items-center gap-2">
                📐 Формула R-Expectancy
              </h3>
              <div className="bg-emerald-500/10 p-4 rounded-lg font-mono text-center mb-4">
                <span className="text-emerald-400 text-lg">E[R] = (Win% × Avg Win R) − (Loss% × Avg Loss R)</span>
              </div>
              <div className="grid md:grid-cols-2 gap-4 text-sm mb-4">
                <div className="text-center">
                  <div className="text-emerald-400 font-bold">Win% × Avg Win R</div>
                  <div className="opacity-60 text-xs">Вероятность победы × средняя прибыль в R</div>
                </div>
                <div className="text-center">
                  <div className="text-red-400 font-bold">Loss% × Avg Loss R</div>
                  <div className="opacity-60 text-xs">Вероятность убытка × средний убыток в R</div>
                </div>
              </div>
            </div>

            {/* Example */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Реальный пример</h3>
              <div className="bg-black/40 rounded-xl p-6 border border-white/10">
                <div className="grid md:grid-cols-2 gap-6 mb-6">
                  <div>
                    <div className="text-xs font-mono uppercase tracking-widest opacity-50 mb-3">Ваша статистика</div>
                    <div className="space-y-2">
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Win Rate:</span>
                        <span className="text-white">45%</span>
                      </div>
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Средняя победа:</span>
                        <span className="text-green-400">+2.5R</span>
                      </div>
                      <div className="flex justify-between p-2 bg-black/30 rounded">
                        <span className="opacity-70">Средний убыток:</span>
                        <span className="text-red-400">−1.0R</span>
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs font-mono uppercase tracking-widest opacity-50 mb-3">Расчёт E[R]</div>
                    <div className="space-y-2">
                      <div className="p-2 bg-green-500/10 rounded border border-green-500/20">
                        <span className="text-green-400">+ 45% × 2.5R = +1.125R</span>
                      </div>
                      <div className="p-2 bg-red-500/10 rounded border border-red-500/20">
                        <span className="text-red-400">− 55% × 1.0R = −0.55R</span>
                      </div>
                      <div className="p-2 bg-emerald-500/20 rounded border border-emerald-500/30">
                        <span className="text-emerald-400 font-bold">E[R] = +0.575R</span>
                      </div>
                    </div>
                  </div>
                </div>
                
                <div className="p-4 bg-emerald-500/10 rounded-lg border border-emerald-500/20 text-center">
                  <div className="text-sm opacity-70 mb-2">При риске 10,000₽ на сделку:</div>
                  <div className="text-2xl font-black text-emerald-400">+5,750₽ средняя прибыль на сделку</div>
                  <div className="text-xs opacity-50 mt-1">0.575 × 10,000₽ = 5,750₽</div>
                </div>
              </div>
            </div>

            {/* Interpretation */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📈 Интерпретация E[R]</h3>
              <div className="space-y-3">
                <div className="flex items-center gap-4 p-3 bg-red-500/10 rounded-lg border border-red-500/20">
                  <div className="w-24 text-right font-mono font-bold text-red-400">&lt; 0R</div>
                  <div className="flex-1">
                    <div className="font-bold text-red-400">Убыточная система</div>
                    <div className="text-xs opacity-60">Каждая сделка в среднем теряет деньги</div>
                  </div>
                </div>
                <div className="flex items-center gap-4 p-3 bg-yellow-500/10 rounded-lg border border-yellow-500/20">
                  <div className="w-24 text-right font-mono font-bold text-yellow-400">0−0.3R</div>
                  <div className="flex-1">
                    <div className="font-bold text-yellow-400">Слабая система</div>
                    <div className="text-xs opacity-60">Прибыль есть, но съедается комиссиями</div>
                  </div>
                </div>
                <div className="flex items-center gap-4 p-3 bg-green-500/10 rounded-lg border border-green-500/20">
                  <div className="w-24 text-right font-mono font-bold text-green-400">0.3−0.7R</div>
                  <div className="flex-1">
                    <div className="font-bold text-green-400">Хорошая система</div>
                    <div className="text-xs opacity-60">Стабильный заработок</div>
                  </div>
                </div>
                <div className="flex items-center gap-4 p-3 bg-emerald-500/20 rounded-lg border border-emerald-500/30">
                  <div className="w-24 text-right font-mono font-bold text-emerald-400">&gt; 0.7R</div>
                  <div className="flex-1">
                    <div className="font-bold text-emerald-400">Отличная система</div>
                    <div className="text-xs opacity-60">Очень прибыльно, проверьте на переоптимизацию</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-emerald-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-emerald-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-emerald-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 E[R] важнее Win Rate — можно выигрывать 30% сделок и быть прибыльным</li>
                <li>📊 Следите за средним R-multiple каждой сделки — он должен расти</li>
                <li>⚠️ E[R] &lt; 0.2R — комиссии и проскальзывание съедят прибыль</li>
                <li>🎯 Eqio рассчитывает R-Expectancy автоматически</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Win/Loss Streaks */}
        <section id="streaks" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 right-0 w-80 h-80 bg-amber-500/15 rounded-full blur-3xl" />
          <div className="absolute -bottom-20 left-0 w-60 h-60 bg-orange-500/10 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-amber-500 to-orange-600 rounded-xl shadow-lg shadow-amber-500/20">
                  <Repeat size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Win/Loss Streaks</h2>
                    <span className="px-2 py-0.5 bg-amber-500/20 rounded text-[10px] font-mono text-amber-400">СЕРИИ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">АНАЛИЗ ПОСЛЕДОВАТЕЛЬНОСТЕЙ ПОБЕД И ПОРАЖЕНИЙ</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <AlertTriangle size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Эмоциональные качели</div>
                  <p className="text-sm opacity-80">
                    5 убытков подряд — и вы ломаетесь. Увеличиваете риск, ломаете правила. 
                    <span className="text-white font-medium"> А что, если бы вы знали, что это нормально?</span>
                  </p>
                </div>
              </div>
            </div>

            {/* What are Streaks */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <Repeat className="text-amber-400" size={18} />
                Зачем анализировать серии?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Серии побед и поражений — это <strong className="text-white">неизбежная часть трейдинга</strong>. 
                Математика гарантирует, что даже у прибыльной системы будут чёрные полосы. 
                Знание максимальных серий помогает <strong className="text-amber-400">психологически подготовиться</strong> и не сломаться.
              </p>
              <div className="bg-amber-500/10 p-4 rounded-lg border border-amber-500/20">
                <p className="text-sm italic text-center">
                  «Серия из 10 убытков — это не провал системы. Это <span className="text-amber-400 font-bold">статистическая неизбежность</span>.»
                </p>
              </div>
            </div>

            {/* Expected Streaks Table */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Ожидаемые серии убытков</h3>
              <p className="text-sm opacity-70 mb-4">
                Какую максимальную серию убытков ожидать при разном Win Rate (на 100 сделок):
              </p>
              
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10">
                      <th className="text-left p-3 opacity-50 font-mono text-xs">Win Rate</th>
                      <th className="text-center p-3 opacity-50 font-mono text-xs">Ожидаемая серия</th>
                      <th className="text-center p-3 opacity-50 font-mono text-xs">Возможная серия (5%)</th>
                      <th className="text-left p-3 opacity-50 font-mono text-xs">Комментарий</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-green-400">70%</td>
                      <td className="p-3 text-center">3−4</td>
                      <td className="p-3 text-center text-yellow-400">6−7</td>
                      <td className="p-3 text-xs opacity-60">Высокий WR, короткие серии</td>
                    </tr>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-yellow-400">50%</td>
                      <td className="p-3 text-center">6−7</td>
                      <td className="p-3 text-center text-orange-400">10−12</td>
                      <td className="p-3 text-xs opacity-60">Как монетка — серии неизбежны</td>
                    </tr>
                    <tr className="border-b border-white/5 hover:bg-white/5">
                      <td className="p-3 font-mono text-orange-400">40%</td>
                      <td className="p-3 text-center">8−10</td>
                      <td className="p-3 text-center text-red-400">14−16</td>
                      <td className="p-3 text-xs opacity-60">Трендовая система — нужна стойкость</td>
                    </tr>
                    <tr className="hover:bg-white/5">
                      <td className="p-3 font-mono text-red-400">30%</td>
                      <td className="p-3 text-center">12−14</td>
                      <td className="p-3 text-center text-red-500 font-bold">20+</td>
                      <td className="p-3 text-xs opacity-60">⚠️ Тяжело психологически</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Your Stats */}
            <div className="bg-gradient-to-r from-amber-500/10 via-orange-500/10 to-amber-500/10 rounded-xl p-6 mb-8 border border-amber-500/20">
              <h3 className="text-white font-bold text-lg mb-4">📈 Что Eqio показывает</h3>
              
              <div className="grid md:grid-cols-2 gap-6">
                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="text-green-400 font-bold mb-3 flex items-center gap-2">
                    🏆 Серии побед
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Текущая серия:</span>
                      <span className="text-green-400 font-bold">3 подряд</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Максимальная:</span>
                      <span className="text-green-400 font-bold">8 подряд</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Средняя:</span>
                      <span>2.4</span>
                    </div>
                  </div>
                </div>
                
                <div className="bg-black/30 p-4 rounded-lg">
                  <div className="text-red-400 font-bold mb-3 flex items-center gap-2">
                    💀 Серии убытков
                  </div>
                  <div className="space-y-2 text-sm">
                    <div className="flex justify-between">
                      <span className="opacity-60">Текущая серия:</span>
                      <span className="text-white">0</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Максимальная:</span>
                      <span className="text-red-400 font-bold">6 подряд</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="opacity-60">Средняя:</span>
                      <span>1.8</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Visual Timeline */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Визуализация серий (пример)</h3>
              <div className="bg-black/40 p-4 rounded-lg border border-white/10">
                <div className="flex flex-wrap gap-1">
                  {/* Win streak */}
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  {/* Loss */}
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  {/* Win */}
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  {/* Loss streak */}
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-red-500 rounded border-2 border-red-300" title="Max Loss Streak!" />
                  {/* Recovery */}
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-green-500 rounded" title="Win" />
                  <div className="w-6 h-6 bg-red-500 rounded" title="Loss" />
                </div>
                <div className="mt-4 flex items-center gap-4 text-xs">
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-green-500 rounded" />
                    <span className="opacity-60">Победа</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-red-500 rounded" />
                    <span className="opacity-60">Убыток</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <div className="w-3 h-3 bg-red-500 rounded border border-red-300" />
                    <span className="opacity-60">Макс. серия убытков</span>
                  </div>
                </div>
              </div>
            </div>

            {/* How to use */}
            <div className="bg-black/40 rounded-xl p-6 mb-8 border border-white/10">
              <h3 className="text-white font-bold text-lg mb-4">💡 Как использовать эту информацию</h3>
              
              <div className="space-y-4">
                <div className="p-4 bg-amber-500/10 rounded-lg border border-amber-500/20">
                  <div className="font-bold text-amber-400 mb-2">1. Психологическая подготовка</div>
                  <p className="text-sm opacity-80">
                    Если ваш Win Rate = 50%, знайте: серия из 10 убытков подряд — это <strong className="text-white">нормально</strong>. 
                    Не паникуйте, не увеличивайте риск.
                  </p>
                </div>
                
                <div className="p-4 bg-amber-500/10 rounded-lg border border-amber-500/20">
                  <div className="font-bold text-amber-400 mb-2">2. Размер позиции</div>
                  <p className="text-sm opacity-80">
                    Рассчитайте, сможете ли вы пережить максимальную серию убытков при текущем риске.
                    6 убытков × 2% = −12% депозита. Выдержите?
                  </p>
                </div>
                
                <div className="p-4 bg-amber-500/10 rounded-lg border border-amber-500/20">
                  <div className="font-bold text-amber-400 mb-2">3. Правило «Стоп на день»</div>
                  <p className="text-sm opacity-80">
                    3 убытка подряд = остановка торговли на сегодня. 
                    <strong className="text-white"> Защита от тильта и эмоциональных решений.</strong>
                  </p>
                </div>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-amber-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-amber-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-amber-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 После 3 убытков подряд — <strong className="text-white">уменьшите размер позиции</strong> вдвое</li>
                <li>📊 Ведите дневник эмоций во время серий — найдёте паттерны</li>
                <li>⚠️ Никогда не увеличивайте риск после серии убытков!</li>
                <li>🎯 Eqio считает серии автоматически и предупреждает о рекордах</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Tags System - add id */}
        <section id="tags" className="cyber-card p-8 relative overflow-hidden">
          {/* Background */}
          <div className="absolute -top-20 right-0 w-60 h-60 bg-pink-500/15 rounded-full blur-3xl" />
          
          <div className="relative">
            {/* Header */}
            <div className="flex items-start justify-between mb-6">
              <div className="flex items-center gap-4">
                <div className="p-3 bg-gradient-to-br from-pink-500 to-pink-700 rounded-xl shadow-lg shadow-pink-500/20">
                  <Tag size={28} className="text-white" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-black tracking-tight">Система тегов</h2>
                    <span className="px-2 py-0.5 bg-pink-500/20 rounded text-[10px] font-mono text-pink-400">ПСИХОЛОГИЯ</span>
                  </div>
                  <p className="text-xs font-mono opacity-50">TAGGING PROTOCOL • САМОАНАЛИЗ</p>
                </div>
              </div>
            </div>

            {/* Pain Point */}
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4 mb-6">
              <div className="flex items-start gap-3">
                <div className="p-1.5 bg-red-500/20 rounded shrink-0">
                  <Brain size={16} className="text-red-400" />
                </div>
                <div>
                  <div className="font-bold text-red-400 mb-1">Враг внутри</div>
                  <p className="text-sm opacity-80">
                    «Я плохо торгую шорты» — думаете вы. Но данные могут показать, что вы теряете только когда 
                    торгуете шорты <strong className="text-white">+ на новостях + после серии убытков</strong>. 
                    Система тегов превращает интуицию в факты.
                  </p>
                </div>
              </div>
            </div>

            {/* What is tagging */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-3 flex items-center gap-2">
                <BookOpen className="text-pink-400" size={18} />
                Зачем нужны теги?
              </h3>
              <p className="text-sm opacity-80 leading-relaxed mb-4">
                Теги позволяют <strong className="text-white">категоризировать сделки</strong> по любым параметрам: 
                эмоциональное состояние, тип сетапа, время дня, новости и т.д. 
                А потом — анализировать статистику по каждой категории.
              </p>
              <div className="bg-pink-500/10 p-4 rounded-lg border border-pink-500/20">
                <p className="text-sm italic text-center">
                  «Данные не лгут. Теги превращают вашу психологию в сухие цифры, 
                  которые можно <span className="text-pink-400 font-bold">измерить и улучшить</span>.»
                </p>
              </div>
            </div>

            {/* Emotional Tags */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">😤 Эмоциональные теги (красные флаги)</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20 hover:border-red-500/40 transition-colors">
                  <div className="text-red-400 font-mono font-bold mb-2">#FOMO</div>
                  <p className="text-xs opacity-70 mb-2">Fear Of Missing Out — страх упустить движение</p>
                  <div className="text-[10px] text-red-400/70">⚠️ Обычно убыточные входы</div>
                </div>
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20 hover:border-red-500/40 transition-colors">
                  <div className="text-red-400 font-mono font-bold mb-2">#REVENGE</div>
                  <p className="text-xs opacity-70 mb-2">Попытка «отыграться» после убытка</p>
                  <div className="text-[10px] text-red-400/70">⚠️ Увеличенный риск, эмоции</div>
                </div>
                <div className="bg-red-500/10 p-4 rounded-lg border border-red-500/20 hover:border-red-500/40 transition-colors">
                  <div className="text-red-400 font-mono font-bold mb-2">#TILT</div>
                  <p className="text-xs opacity-70 mb-2">Полная потеря контроля</p>
                  <div className="text-[10px] text-red-400/70">🚨 Критический красный флаг</div>
                </div>
                <div className="bg-orange-500/10 p-4 rounded-lg border border-orange-500/20 hover:border-orange-500/40 transition-colors">
                  <div className="text-orange-400 font-mono font-bold mb-2">#IMPULSE</div>
                  <p className="text-xs opacity-70 mb-2">Спонтанная сделка без плана</p>
                  <div className="text-[10px] text-orange-400/70">⚠️ Нарушение дисциплины</div>
                </div>
                <div className="bg-orange-500/10 p-4 rounded-lg border border-orange-500/20 hover:border-orange-500/40 transition-colors">
                  <div className="text-orange-400 font-mono font-bold mb-2">#OVERSIZE</div>
                  <p className="text-xs opacity-70 mb-2">Завышенный размер позиции</p>
                  <div className="text-[10px] text-orange-400/70">⚠️ Нарушение риск-менеджмента</div>
                </div>
                <div className="bg-yellow-500/10 p-4 rounded-lg border border-yellow-500/20 hover:border-yellow-500/40 transition-colors">
                  <div className="text-yellow-400 font-mono font-bold mb-2">#LATE</div>
                  <p className="text-xs opacity-70 mb-2">Слишком поздний вход</p>
                  <div className="text-[10px] text-yellow-400/70">Правильное направление, плохой тайминг</div>
                </div>
              </div>
            </div>

            {/* Positive Tags */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">✅ Позитивные теги (зелёные флаги)</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 hover:border-green-500/40 transition-colors">
                  <div className="text-green-400 font-mono font-bold mb-2">#SYSTEM</div>
                  <p className="text-xs opacity-70 mb-2">Идеальный вход по правилам системы</p>
                  <div className="text-[10px] text-green-400/70">✓ Эталонная сделка</div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 hover:border-green-500/40 transition-colors">
                  <div className="text-green-400 font-mono font-bold mb-2">#A_SETUP</div>
                  <p className="text-xs opacity-70 mb-2">Лучший сетап, все условия сошлись</p>
                  <div className="text-[10px] text-green-400/70">✓ Максимальная уверенность</div>
                </div>
                <div className="bg-green-500/10 p-4 rounded-lg border border-green-500/20 hover:border-green-500/40 transition-colors">
                  <div className="text-green-400 font-mono font-bold mb-2">#PATIENT</div>
                  <p className="text-xs opacity-70 mb-2">Дождались идеального входа</p>
                  <div className="text-[10px] text-green-400/70">✓ Дисциплина и терпение</div>
                </div>
              </div>
            </div>

            {/* Context Tags */}
            <div className="mb-8">
              <h3 className="text-white font-bold text-lg mb-4">📊 Контекстные теги</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#NEWS</div>
                  <div className="text-[10px] opacity-50">На новостях</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#TREND</div>
                  <div className="text-[10px] opacity-50">По тренду</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#COUNTER</div>
                  <div className="text-[10px] opacity-50">Контртренд</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#BREAKOUT</div>
                  <div className="text-[10px] opacity-50">Пробой уровня</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#PULLBACK</div>
                  <div className="text-[10px] opacity-50">Откат</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#MORNING</div>
                  <div className="text-[10px] opacity-50">Утренняя сессия</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#EVENING</div>
                  <div className="text-[10px] opacity-50">Вечерняя сессия</div>
                </div>
                <div className="bg-accent/10 p-3 rounded-lg border border-accent/20 text-center">
                  <div className="text-accent font-mono text-sm font-bold">#EARNINGS</div>
                  <div className="text-[10px] opacity-50">Отчётность</div>
                </div>
              </div>
            </div>

            {/* Example Analysis */}
            <div className="bg-gradient-to-r from-pink-500/10 via-accent/10 to-pink-500/10 rounded-xl p-6 mb-8 border border-pink-500/20">
              <h3 className="text-white font-bold text-lg mb-4">📊 Пример анализа по тегам</h3>
              
              <div className="bg-black/30 p-4 rounded-lg mb-4">
                <div className="text-sm opacity-80 mb-4">
                  Трейдер думал, что плохо торгует шорты. Eqio показал реальную картину:
                </div>
                
                <div className="space-y-2">
                  <div className="flex justify-between items-center p-2 bg-black/30 rounded">
                    <span className="font-mono text-sm">#SHORT</span>
                    <span className="text-green-400">+12% (прибыльно!)</span>
                  </div>
                  <div className="flex justify-between items-center p-2 bg-black/30 rounded">
                    <span className="font-mono text-sm">#SHORT + #NEWS</span>
                    <span className="text-yellow-400">−3% (слабо)</span>
                  </div>
                  <div className="flex justify-between items-center p-2 bg-red-500/10 rounded border border-red-500/20">
                    <span className="font-mono text-sm">#SHORT + #NEWS + #REVENGE</span>
                    <span className="text-red-400 font-bold">−45% (катастрофа!)</span>
                  </div>
                </div>
              </div>
              
              <div className="bg-accent/10 p-4 rounded border border-accent/20">
                <div className="font-bold text-accent mb-2">💡 Вывод:</div>
                <p className="text-sm opacity-80">
                  Проблема не в шортах! Проблема в комбинации: новости + желание отыграться. 
                  <strong className="text-white"> Решение: не торговать шорты на новостях после убытков.</strong>
                </p>
              </div>
            </div>

            {/* Pro Tips */}
            <div className="border-l-4 border-pink-500 pl-4 py-2">
              <div className="flex items-center gap-2 mb-2">
                <Crown size={16} className="text-pink-400" />
                <span className="text-sm font-bold uppercase tracking-wider text-pink-400">Советы профессионалов</span>
              </div>
              <ul className="space-y-2 text-sm opacity-80">
                <li>💡 Ставьте теги <strong className="text-white">сразу при открытии</strong> — потом забудете эмоции</li>
                <li>📊 Анализируйте теги еженедельно — ищите паттерны</li>
                <li>⚠️ Если #FOMO или #REVENGE встречаются часто — это сигнал для работы над психологией</li>
                <li>🎯 Создавайте свои теги под вашу стратегию!</li>
              </ul>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
