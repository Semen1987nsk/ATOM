'use client';

/**
 * Phase 14 (2026-05-17, fixed 2026-05-18): Top sticky horizontal scrollbar.
 *
 * Дублирует bottom scrollbar основного scroll-контейнера и располагается
 * sticky прямо под NavigatorBar — пользователь может прокрутить таблицу
 * вправо/влево из любой вертикальной позиции, без скролла страницы вниз.
 *
 * Pattern: jQuery DataTables / Bootstrap Tables / GitHub diff view.
 *
 * BUGFIX (2026-05-18): прошлая версия использовала `useEffect(..., [mainScrollRef])`.
 * Ref-объект референтно стабилен (его identity не меняется), поэтому эффект
 * запускался только один раз на mount — когда mainScrollRef.current === null
 * (таблица ещё не отрендерена из-за loading=true). Listeners никогда не
 * привязывались. Решение: callback ref на TopScrollbar + перевязка handler'ов
 * через useEffect, который реагирует на изменение DOM-узла (через локальный
 * state) или scrollWidth (signal что parent смонтировал table).
 */
import { useCallback, useEffect, useRef, useState } from 'react';

interface Props {
  /** Ref на основной overflow-x scroll контейнер (тот что уже есть в журнале). */
  mainScrollRef: React.RefObject<HTMLDivElement | null>;
  /**
   * Ширина прокручиваемой области (scrollWidth таблицы). Передаётся из
   * parent через ResizeObserver. Если 0 — top scrollbar скрыт (нет overflow).
   * Также используется как dep effect'а: когда становится >0, parent смонтировал
   * scroll container → можем привязать handler'ы.
   */
  scrollWidth: number;
}

export function TableTopScrollbar({ mainScrollRef, scrollWidth }: Props) {
  /** Локальный state-DOM-ref: setTopNode вызывается React'ом при mount/unmount
   *  элемента, что триггерит useEffect при появлении DOM-узла. */
  const [topNode, setTopNode] = useState<HTMLDivElement | null>(null);
  const setTopRef = useCallback((node: HTMLDivElement | null) => {
    setTopNode(node);
  }, []);
  /**
   * Guard против infinite sync loop: когда мы программно меняем scrollLeft
   * у одного контейнера, его onScroll сработает и попытается обратно
   * синхронизировать второй. Flag блокирует обратный путь до next frame.
   */
  const syncing = useRef(false);

  useEffect(() => {
    const topEl = topNode;
    const mainEl = mainScrollRef.current;
    // Эффект перезапускается каждый раз когда scrollWidth меняется (родитель
    // вызвал ResizeObserver-callback) ИЛИ когда topNode появляется. Это
    // гарантирует что mainEl уже не null к моменту привязки listener'ов.
    if (!topEl || !mainEl) return;

    const handleTopScroll = () => {
      if (syncing.current) return;
      syncing.current = true;
      mainEl.scrollTo({ left: topEl.scrollLeft, behavior: 'instant' });
      requestAnimationFrame(() => {
        syncing.current = false;
      });
    };
    const handleMainScroll = () => {
      if (syncing.current) return;
      syncing.current = true;
      topEl.scrollTo({ left: mainEl.scrollLeft, behavior: 'instant' });
      requestAnimationFrame(() => {
        syncing.current = false;
      });
    };

    topEl.addEventListener('scroll', handleTopScroll, { passive: true });
    mainEl.addEventListener('scroll', handleMainScroll, { passive: true });
    // Sync на старте: подтянуть top к текущей scrollLeft основного.
    topEl.scrollTo({ left: mainEl.scrollLeft, behavior: 'instant' });
    return () => {
      topEl.removeEventListener('scroll', handleTopScroll);
      mainEl.removeEventListener('scroll', handleMainScroll);
    };
  }, [topNode, mainScrollRef, scrollWidth]);

  const needsScroll = scrollWidth > 0;

  return (
    <div
      ref={setTopRef}
      className="sticky top-14 overflow-x-auto scrollbar-visible bg-[#0d0d0d]/95 backdrop-blur-sm border-b border-slate-800"
      style={{
        height: 14,
        display: needsScroll ? 'block' : 'none',
        zIndex: 15, // выше thead (z-5), ниже NavigatorBar dropdowns (z-30+)
      }}
      aria-hidden="true"
    >
      <div style={{ width: scrollWidth, height: 1 }} />
    </div>
  );
}
