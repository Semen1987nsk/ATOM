'use client';

import Link from 'next/link';
import { ArrowLeft, Zap, Activity, Target, TrendingUp, BookOpen, AlertTriangle, GitGraph } from 'lucide-react';

export default function Manual() {
  return (
    <main className="min-h-screen p-8 max-w-4xl mx-auto">
      <header className="mb-12">
        <Link href="/" className="inline-flex items-center gap-2 text-accent hover:text-white transition-colors mb-6 font-mono text-xs uppercase tracking-widest">
          <ArrowLeft size={14} /> Return to Terminal
        </Link>
        <h1 className="text-4xl font-black tracking-tighter mb-2 italic">
          SYSTEM <span className="text-accent">MANUAL</span>
        </h1>
        <p className="text-xs font-mono opacity-50 uppercase tracking-[0.2em]">
          Protocol Documentation v1.0
        </p>
      </header>

      <div className="space-y-12">
        {/* Optimal f */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <Zap className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">Optimal f (Ralph Vince)</h2>
          </div>
          <div className="space-y-6 text-sm opacity-80 leading-relaxed">
            <div className="bg-accent/5 p-4 border-l-2 border-accent italic text-white">
              &quot;Математическая формула богатства. Как превратить $1,000 в $1,000,000 быстрее всего?&quot;
            </div>
            
            <div>
              <h3 className="text-white font-bold mb-2 text-lg">Простая аналогия</h3>
              <p className="mb-2">
                Представьте, что у вас есть магическая монета. Орел выпадает в 60% случаев (вы выигрываете 2x ставки), Решка — в 40% (вы теряете ставку).
              </p>
              <ul className="list-disc pl-5 space-y-1 mb-2">
                <li>Если вы будете ставить <strong>100%</strong> банка, то при первой же Решке вы потеряете всё. Банкрот.</li>
                <li>Если вы будете ставить <strong>1%</strong> банка, вы будете богатеть, но очень медленно.</li>
              </ul>
              <p>
                Где-то между 1% и 100% есть <strong>идеальный процент (Optimal f)</strong>, при котором ваш капитал растет с максимальной геометрической скоростью. Для этой монеты это, скажем, 20%. Ставя именно 20%, вы обгоните любого другого игрока на дистанции.
              </p>
            </div>

            <div>
              <h3 className="text-white font-bold mb-2 text-lg">Как это работает в ATOM?</h3>
              <p>
                ATOM анализирует историю ваших сделок (ваши победы и поражения) и вычисляет этот идеальный процент риска именно для ВАШЕЙ стратегии.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6 bg-black/40 p-4 rounded border border-white/5">
              <div>
                <h4 className="text-accent font-mono text-xs uppercase mb-2">Трейдер "Интуиция" (Риск 2%)</h4>
                <p className="text-xs">Торгует фиксированным лотом. За год превращает $10,000 в $15,000. Неплохо, но линейно.</p>
              </div>
              <div>
                <h4 className="text-accent font-mono text-xs uppercase mb-2">Трейдер "ATOM" (Optimal f = 14%)</h4>
                <p className="text-xs">Использует сложный процент. За тот же год, на тех же сделках, превращает $10,000 в $48,000. Это сила геометрии.</p>
              </div>
            </div>

            <div className="bg-red-500/10 p-4 border-l-2 border-red-500 font-mono text-xs mt-4">
              <strong className="text-red-400">ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ:</strong> Торговля на полном Optimal f (1.0) — это "американские горки". Просадки могут достигать 70%. 
              <br/><br/>
              Мы рекомендуем использовать <strong>Fractional f (Дробный f)</strong>. Например, если ATOM говорит, что Optimal f = 0.20 (20%), торгуйте с риском 10% (Half-Kelly). Вы получите 75% от максимальной доходности, но с вдвое меньшими нервами.
            </div>
          </div>
        </section>

        {/* SQN */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <Activity className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">System Quality Number (SQN)</h2>
          </div>
          <div className="space-y-6 text-sm opacity-80 leading-relaxed">
            <div className="bg-accent/5 p-4 border-l-2 border-accent italic text-white">
              &quot;Кредитный рейтинг вашей стратегии. Насколько легко торговать вашу систему?&quot;
            </div>

            <div>
              <h3 className="text-white font-bold mb-2 text-lg">Что это такое?</h3>
              <p>
                Представьте, что вы едете из точки А в точку Б.
              </p>
              <ul className="list-disc pl-5 space-y-1 mt-2">
                <li><strong>Низкий SQN</strong>: Вы едете на старом джипе по болоту. Вас трясет, укачивает, вы застреваете (просадки), но в итоге доезжаете.</li>
                <li><strong>Высокий SQN</strong>: Вы летите бизнес-классом. Тихо, спокойно, быстро.</li>
              </ul>
              <p className="mt-2">
                SQN измеряет соотношение вашей прибыли к "тряске" (волатильности результатов). Чем выше SQN, тем стабильнее растет график доходности.
              </p>
            </div>

            <div>
              <h3 className="text-white font-bold mb-2 text-lg">Шкала оценки (Ван Тарп)</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-xs">
                <div className="p-3 bg-white/5 rounded border border-white/5">
                  <span className="text-red-400 font-bold block text-sm">SQN &lt; 1.6 (Слабо)</span>
                  <span className="opacity-50">Трудно торговать. Скорее всего, вы сольете из-за психологии.</span>
                </div>
                <div className="p-3 bg-white/5 rounded border border-white/5">
                  <span className="text-yellow-400 font-bold block text-sm">1.6 - 2.0 (Средне)</span>
                  <span className="opacity-50">Рабочая лошадка. Большинство прибыльных систем здесь.</span>
                </div>
                <div className="p-3 bg-white/5 rounded border border-white/5">
                  <span className="text-green-400 font-bold block text-sm">2.0 - 3.0 (Хорошо)</span>
                  <span className="opacity-50">Отличная система. Можно смело увеличивать капитал.</span>
                </div>
                <div className="p-3 bg-white/5 rounded border border-white/5">
                  <span className="text-accent font-bold block text-sm">SQN &gt; 5.0 (Грааль)</span>
                  <span className="opacity-50">Печатный станок. Встречается крайне редко.</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Z-Score */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <GitGraph className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">Z-Score (Серийность)</h2>
          </div>
          <div className="space-y-6 text-sm opacity-80 leading-relaxed">
            <div className="bg-accent/5 p-4 border-l-2 border-accent italic text-white">
              &quot;Есть ли у вашей удачи память? Стоит ли повышать ставки, когда везет?&quot;
            </div>

            <div>
              <h3 className="text-white font-bold mb-2 text-lg">Суть показателя</h3>
              <p>
                Z-Score отвечает на один главный вопрос: <strong>Зависит ли исход следующей сделки от предыдущей?</strong>
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-4 font-mono text-xs">
              <div className="bg-black/40 p-4 rounded border border-white/5 flex flex-col">
                <h4 className="text-green-400 font-bold mb-2 text-sm">Z &lt; -1.96 (Стрики)</h4>
                <p className="opacity-70 mb-4 flex-grow">
                  "Победы притягивают победы". У вас бывают длинные белые и черные полосы.
                </p>
                <div className="bg-green-500/10 p-2 rounded border border-green-500/30">
                  <strong className="text-green-400 block mb-1">Совет:</strong>
                  Выиграли? Увеличивайте лот! Проиграли? Снижайте до минимума и ждите конца черной полосы.
                </div>
              </div>
              
              <div className="bg-black/40 p-4 rounded border border-white/5 flex flex-col">
                <h4 className="text-white font-bold mb-2 text-sm">Z ≈ 0 (Случайность)</h4>
                <p className="opacity-70 mb-4 flex-grow">
                  Как подбрасывание монеты. Прошлая сделка никак не влияет на будущую.
                </p>
                <div className="bg-white/10 p-2 rounded border border-white/30">
                  <strong className="text-white block mb-1">Совет:</strong>
                  Используйте стандартный риск-менеджмент. Не пытайтесь угадать серию.
                </div>
              </div>

              <div className="bg-black/40 p-4 rounded border border-white/5 flex flex-col">
                <h4 className="text-red-400 font-bold mb-2 text-sm">Z &gt; 1.96 (Пила)</h4>
                <p className="opacity-70 mb-4 flex-grow">
                  "Плюс-минус-плюс". Результаты постоянно чередуются.
                </p>
                <div className="bg-red-500/10 p-2 rounded border border-red-500/30">
                  <strong className="text-red-400 block mb-1">Совет:</strong>
                  Парадокс! Увеличивайте лот ПОСЛЕ убытка (ждем прибыль). Уменьшайте ПОСЛЕ прибыли (ждем убыток).
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Advanced Metrics */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <TrendingUp className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">Advanced Efficiency Metrics</h2>
          </div>
          <div className="space-y-8 text-sm opacity-80 leading-relaxed">
            
            {/* Profit Factor */}
            <div>
              <h3 className="text-white font-bold text-lg mb-2 flex items-center gap-2">
                1. Profit Factor <span className="text-xs font-mono opacity-50 bg-white/10 px-2 py-1 rounded">Gross Profit / Gross Loss</span>
              </h3>
              <p className="mb-3">
                Самый честный детектор лжи. Показывает, сколько долларов прибыли вы получаете на каждый доллар убытка.
              </p>
              <div className="bg-black/40 p-4 rounded border border-white/5 mb-3">
                <p className="text-xs mb-2"><strong>Пример:</strong> За месяц вы заработали $5,000 (сумма всех прибыльных сделок) и потеряли $2,500 (сумма всех убыточных).</p>
                <code className="text-accent font-mono text-xs">Profit Factor = 5000 / 2500 = 2.0</code>
              </div>
              <div className="grid grid-cols-3 gap-2 font-mono text-xs text-center">
                <div className="bg-red-500/10 border border-red-500/30 p-2 rounded">
                  <div className="text-red-400 font-bold text-lg">&lt; 1.0</div>
                  <div className="opacity-70">Система теряет деньги</div>
                </div>
                <div className="bg-yellow-500/10 border border-yellow-500/30 p-2 rounded">
                  <div className="text-yellow-400 font-bold text-lg">1.5 - 2.0</div>
                  <div className="opacity-70">Хорошая рабочая система</div>
                </div>
                <div className="bg-green-500/10 border border-green-500/30 p-2 rounded">
                  <div className="text-green-400 font-bold text-lg">&gt; 3.0</div>
                  <div className="opacity-70">Элитный уровень</div>
                </div>
              </div>
            </div>

            {/* R-Expectancy */}
            <div>
              <h3 className="text-white font-bold text-lg mb-2 flex items-center gap-2">
                2. R-Expectancy <span className="text-xs font-mono opacity-50 bg-white/10 px-2 py-1 rounded">Van Tharp&apos;s Edge</span>
              </h3>
              <p className="mb-3">
                Матожидание вашей системы, выраженное в рисках (R). Отвечает на вопрос: &quot;Если я рискну $100, сколько я в среднем заработаю?&quot;
              </p>
              <div className="bg-black/40 p-4 rounded border border-white/5">
                <ul className="space-y-2 text-xs">
                  <li className="flex gap-2">
                    <span className="text-accent font-bold">0.5R:</span>
                    <span>На каждые $100 риска вы зарабатываете $50 (в среднем за сделку). Это отличный результат.</span>
                  </li>
                  <li className="flex gap-2">
                    <span className="text-red-400 font-bold">-0.2R:</span>
                    <span>Казино (Рулетка). Вы платите $20 за право сыграть на $100. На дистанции вы гарантированно проиграете.</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Recovery Factor */}
            <div>
              <h3 className="text-white font-bold text-lg mb-2 flex items-center gap-2">
                3. Recovery Factor <span className="text-xs font-mono opacity-50 bg-white/10 px-2 py-1 rounded">Net Profit / Max Drawdown</span>
              </h3>
              <p className="mb-3">
                Показатель &quot;живучести&quot; и стрессоустойчивости. Показывает, насколько быстро система выбирается из просадок.
              </p>
              <div className="grid md:grid-cols-2 gap-4 text-xs">
                <div className="p-3 border border-border">
                  <strong className="text-white block mb-1">Система А (RF = 1.0)</strong>
                  Заработала $10,000, но перед этим просела на $10,000. 
                  <br/><span className="text-red-400">Вердикт: Опасно. Вы сидели на валидоле.</span>
                </div>
                <div className="p-3 border border-border">
                  <strong className="text-white block mb-1">Система Б (RF = 5.0)</strong>
                  Заработала $10,000, максимальная просадка была всего $2,000.
                  <br/><span className="text-accent">Вердикт: Грааль. Идеальная кривая доходности.</span>
                </div>
              </div>
            </div>

            {/* AHPR */}
            <div>
              <h3 className="text-white font-bold text-lg mb-2 flex items-center gap-2">
                4. AHPR <span className="text-xs font-mono opacity-50 bg-white/10 px-2 py-1 rounded">Average Holding Period Return</span>
              </h3>
              <p className="mb-3">
                Средняя доходность за период удержания. Это ваш &quot;процентный двигатель&quot;. Если AHPR = 1.05, это значит, что в среднем каждая сделка увеличивает ваш капитал на 5%.
              </p>
              <div className="bg-black/40 p-4 rounded border border-white/5 text-xs">
                <p className="mb-2">
                  Это ключевой компонент для формулы сложного процента. Чем выше AHPR, тем агрессивнее растет ваша кривая капитала.
                </p>
                <div className="flex gap-4">
                  <div>
                    <span className="text-red-400 font-bold block">AHPR &lt; 1.0</span>
                    <span className="opacity-70">Система сливает</span>
                  </div>
                  <div>
                    <span className="text-accent font-bold block">AHPR &gt; 1.0</span>
                    <span className="opacity-70">Система зарабатывает</span>
                  </div>
                </div>
              </div>
            </div>

          </div>
        </section>

        {/* MAE/MFE */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <Target className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">MAE / MFE Analysis</h2>
          </div>
          <div className="space-y-6 text-sm opacity-80 leading-relaxed">
            <div className="bg-accent/5 p-4 border-l-2 border-accent italic text-white">
              &quot;Деньги, которые вы оставляете на столе.&quot;
            </div>

            <div className="grid md:grid-cols-2 gap-8">
              <div className="space-y-3">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <span className="text-red-400">MAE</span> (Maximum Adverse Excursion)
                </h3>
                <p className="text-xs opacity-70">Максимальная &quot;боль&quot;, которую вы терпели в сделке.</p>
                <div className="bg-black/40 p-3 rounded border border-white/5 text-xs">
                  <strong>Пример:</strong> Ваш Стоп-Лосс = $100. Но анализ показывает, что в прибыльных сделках цена никогда не шла против вас больше чем на $20 (MAE).
                  <br/><br/>
                  <strong>Вывод:</strong> Вы ставите слишком широкие стопы! Уменьшив стоп до $30, вы могли бы увеличить размер позиции в 3 раза и утроить прибыль при том же риске.
                </div>
              </div>
              
              <div className="space-y-3">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <span className="text-green-400">MFE</span> (Maximum Favorable Excursion)
                </h3>
                <p className="text-xs opacity-70">Максимальная &quot;бумажная&quot; прибыль в моменте.</p>
                <div className="bg-black/40 p-3 rounded border border-white/5 text-xs">
                  <strong>Пример:</strong> Вы выходите из сделки с прибылью $200. Но MFE показывает, что цена доходила до $500, прежде чем развернуться.
                  <br/><br/>
                  <strong>Вывод:</strong> Вы &quot;пересиживаете&quot; или слишком рано выходите. ATOM подскажет, где статистически лучше фиксировать прибыль.
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* Tags Strategy */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <BookOpen className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">Tagging Protocol</h2>
          </div>
          <div className="space-y-6 text-sm opacity-80 leading-relaxed">
            <div className="bg-accent/5 p-4 border-l-2 border-accent italic text-white">
              &quot;Познай себя. Данные не лгут.&quot;
            </div>
            
            <p>
              Вы можете думать, что плохо торгуете &quot;Шорты&quot;. Но данные могут показать, что вы теряете деньги только когда торгуете &quot;Шорты&quot; + &quot;На новостях&quot; (#NEWS).
              Система тегов ATOM превращает вашу психологию в сухие цифры.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 font-mono text-xs mt-2">
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#FOMO</span>
                <p className="mt-1 opacity-50">Вход из страха упустить движение. Обычно убыточен.</p>
              </div>
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#REVENGE</span>
                <p className="mt-1 opacity-50">Попытка &quot;отыграться&quot; сразу после лосса. Опасно!</p>
              </div>
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#TILT</span>
                <p className="mt-1 opacity-50">Полная потеря контроля. Красный флаг.</p>
              </div>
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#SYSTEM</span>
                <p className="mt-1 opacity-50">Идеальный вход по правилам. Эталон.</p>
              </div>
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#IMPULSE</span>
                <p className="mt-1 opacity-50">Спонтанная сделка без плана.</p>
              </div>
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#LATE</span>
                <p className="mt-1 opacity-50">Правильное направление, но слишком поздний вход.</p>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
