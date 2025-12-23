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
              "Перестаньте гадать с размером позиции. Позвольте математике максимизировать ваше богатство."
            </div>
            
            <div>
              <h3 className="text-white font-bold mb-2">Почему это важно?</h3>
              <p>
                Большинство трейдеров выбирают риск случайно (например, "буду рисковать 1%"). Но почему 1%, а не 0.5% или 3%? 
                Optimal f отвечает на этот вопрос математически точно. Это та доля капитала, при которой ваш депозит будет расти с максимально возможной скоростью для вашей конкретной стратегии.
              </p>
            </div>

            <div>
              <h3 className="text-white font-bold mb-2">История</h3>
              <p>
                В 1990-х годах Ральф Винс адаптировал формулу Келли для биржевой торговли. В отличие от казино, где выигрыши фиксированы, в трейдинге прибыль всегда разная. Винс создал формулу, которая учитывает распределение всех ваших сделок, чтобы найти "золотую середину" риска.
              </p>
            </div>

            <div className="grid md:grid-cols-2 gap-6 bg-black/40 p-4 rounded border border-white/5">
              <div>
                <h4 className="text-accent font-mono text-xs uppercase mb-2">Трейдер А (Риск 2%)</h4>
                <p className="text-xs">Торгует консервативно. Через 100 сделок превращает $10,000 в $14,000. Безопасно, но медленно.</p>
              </div>
              <div>
                <h4 className="text-accent font-mono text-xs uppercase mb-2">Трейдер Б (Optimal f = 15%)</h4>
                <p className="text-xs">Использует математику. Через 100 сделок превращает $10,000 в $45,000. Тот же рынок, те же входы, но другой результат.</p>
              </div>
            </div>

            <div className="bg-red-500/10 p-4 border-l-2 border-red-500 font-mono text-xs mt-4">
              <strong className="text-red-400">WARNING:</strong> Торговля на полном Optimal f (1.0) психологически трудна — просадки могут достигать 60-80%. ATOM рекомендует использовать "Fractional f" (например, 0.5 от рассчитанного значения) для баланса между ростом и спокойствием.
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
              "Ваша стратегия — это удача или мастерство? SQN знает правду."
            </div>

            <div>
              <h3 className="text-white font-bold mb-2">Зачем это нужно?</h3>
              <p>
                Вы можете заработать 50% за месяц, просто "угадав" одну сделку на весь депозит. Это не мастерство, это казино. 
                SQN (разработанный доктором Ван Тарпом) оценивает <strong>качество</strong> вашей торговли. Он наказывает за волатильность и поощряет стабильность.
              </p>
            </div>

            <div>
              <h3 className="text-white font-bold mb-2">Как это работает</h3>
              <p>
                Система с Win Rate 40%, но стабильными небольшими убытками и хорошими прибылями, может иметь более высокий SQN, чем скальпер с Win Rate 90%, который иногда теряет половину депозита одной сделкой.
              </p>
              <code className="block mt-3 p-3 bg-black border border-accent/20 rounded font-mono text-accent text-xs">
                SQN = (Средняя Прибыль / Стандартное Отклонение) * √Кол-во Сделок
              </code>
            </div>

            <div>
              <h3 className="text-white font-bold mb-2">Шкала Ван Тарпа</h3>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2 font-mono text-xs">
                <li className="p-2 bg-white/5 rounded flex justify-between"><span className="opacity-50">{'< 1.6'}</span> <span className="text-red-400">Poor (Слабая)</span></li>
                <li className="p-2 bg-white/5 rounded flex justify-between"><span className="opacity-50">1.6 - 1.9</span> <span className="text-yellow-400">Average (Средняя)</span></li>
                <li className="p-2 bg-white/5 rounded flex justify-between"><span className="opacity-50">2.0 - 2.9</span> <span className="text-green-400">Good (Хорошая)</span></li>
                <li className="p-2 bg-white/5 rounded flex justify-between"><span className="opacity-50">3.0 - 4.9</span> <span className="text-accent">Excellent (Отличная)</span></li>
                <li className="p-2 bg-white/5 rounded flex justify-between"><span className="opacity-50">5.0 - 6.9</span> <span className="text-purple-400">Superb (Превосходная)</span></li>
                <li className="p-2 bg-white/5 rounded flex justify-between"><span className="opacity-50">7.0+</span> <span className="text-purple-400 animate-pulse">Holy Grail (Грааль)</span></li>
              </ul>
            </div>
          </div>
        </section>

        {/* Z-Score */}
        <section className="cyber-card p-8">
          <div className="flex items-center gap-3 mb-6 border-b border-border pb-4">
            <GitGraph className="text-accent" size={24} />
            <h2 className="text-xl font-bold tracking-tight">Z-Score (Serial Correlation)</h2>
          </div>
          <div className="space-y-6 text-sm opacity-80 leading-relaxed">
            <div className="bg-accent/5 p-4 border-l-2 border-accent italic text-white">
              "Есть ли у вашей системы память? Или каждая сделка — это чистый лист?"
            </div>

            <div>
              <h3 className="text-white font-bold mb-2">Что это такое?</h3>
              <p>
                Z-Score отвечает на вопрос: зависит ли результат следующей сделки от предыдущей? 
                Это критически важно для управления капиталом. Если вы используете Optimal f, вы обязаны знать свой Z-Score.
              </p>
            </div>

            <div className="grid md:grid-cols-3 gap-4 font-mono text-xs">
              <div className="bg-black/40 p-4 rounded border border-white/5">
                <h4 className="text-green-400 font-bold mb-2">Z &lt; -1.96 (Серии)</h4>
                <p className="opacity-70 mb-2">Победы липнут к победам, убытки к убыткам.</p>
                <div className="text-accent">Стратегия:</div>
                <p>Увеличивайте лот в серии побед. Режьте лот сразу после первого убытка.</p>
              </div>
              
              <div className="bg-black/40 p-4 rounded border border-white/5">
                <h4 className="text-white font-bold mb-2">Z ≈ 0 (Случайность)</h4>
                <p className="opacity-70 mb-2">Результаты независимы. Идеально для Optimal f.</p>
                <div className="text-accent">Стратегия:</div>
                <p>Используйте стандартный риск-менеджмент. Результат следующей сделки непредсказуем.</p>
              </div>

              <div className="bg-black/40 p-4 rounded border border-white/5">
                <h4 className="text-red-400 font-bold mb-2">Z &gt; 1.96 (Пила)</h4>
                <p className="opacity-70 mb-2">Плюс сменяется минусом. "Шаг вперед, два назад".</p>
                <div className="text-accent">Стратегия:</div>
                <p>Увеличивайте лот ПОСЛЕ убытка. Уменьшайте ПОСЛЕ прибыли.</p>
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
              "Деньги, которые вы оставляете на столе."
            </div>

            <div className="grid md:grid-cols-2 gap-8">
              <div className="space-y-3">
                <h3 className="font-bold text-white flex items-center gap-2">
                  <span className="text-red-400">MAE</span> (Maximum Adverse Excursion)
                </h3>
                <p className="text-xs opacity-70">Максимальная "боль", которую вы терпели в сделке.</p>
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
                <p className="text-xs opacity-70">Максимальная "бумажная" прибыль в моменте.</p>
                <div className="bg-black/40 p-3 rounded border border-white/5 text-xs">
                  <strong>Пример:</strong> Вы выходите из сделки с прибылью $200. Но MFE показывает, что цена доходила до $500, прежде чем развернуться.
                  <br/><br/>
                  <strong>Вывод:</strong> Вы "пересиживаете" или слишком рано выходите. ATOM подскажет, где статистически лучше фиксировать прибыль.
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
              "Познай себя. Данные не лгут."
            </div>
            
            <p>
              Вы можете думать, что плохо торгуете "Шорты". Но данные могут показать, что вы теряете деньги только когда торгуете "Шорты" + "На новостях" (#NEWS).
              Система тегов ATOM превращает вашу психологию в сухие цифры.
            </p>

            <div className="grid grid-cols-2 md:grid-cols-3 gap-4 font-mono text-xs mt-2">
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#FOMO</span>
                <p className="mt-1 opacity-50">Вход из страха упустить движение. Обычно убыточен.</p>
              </div>
              <div className="p-3 border border-border hover:border-accent transition-colors group">
                <span className="text-accent group-hover:text-white">#REVENGE</span>
                <p className="mt-1 opacity-50">Попытка "отыграться" сразу после лосса. Опасно!</p>
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
