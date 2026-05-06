"use client";
/**
 * useModalState — централизованное управление модалками через useReducer.
 *
 * Заменяет паттерн "13 отдельных useState<boolean>" в page.tsx и других
 * страницах с большим количеством модалок. Гарантирует, что одновременно
 * открыта только ОДНА модалка (поведение, которое часто хотят, но забывают
 * обеспечить вручную).
 *
 * Преимущества:
 * - Один источник правды о текущей модалке.
 * - Легко добавить behavior "при открытии новой модалки закрыть старую".
 * - Payload передаётся вместе с типом — type-safe доступ через `state.payload`.
 *
 * Migration пример (НЕ автоматический, делается вручную):
 *
 *   // Было:
 *   const [showAdd, setShowAdd] = useState(false);
 *   const [showClose, setShowClose] = useState(false);
 *   const [tradeToClose, setTradeToClose] = useState<Trade | null>(null);
 *
 *   // Стало:
 *   const modal = useModalState<{
 *     add: undefined;
 *     close: { trade: Trade };
 *   }>();
 *   modal.open("add");                       // открыть Add
 *   modal.open("close", { trade });          // открыть Close с payload
 *   modal.close();                           // закрыть всё
 *   modal.is("add")                          // проверка
 *   if (modal.is("close")) modal.payload.trade  // type-narrowed payload
 */
import { useCallback, useReducer } from "react";

type ModalRegistry = Record<string, unknown>;

type ModalState<R extends ModalRegistry> =
  | { kind: null; payload: null }
  | { [K in keyof R]: { kind: K; payload: R[K] } }[keyof R];

type Action<R extends ModalRegistry> =
  | { type: "open"; kind: keyof R; payload: R[keyof R] }
  | { type: "close" };

function reducer<R extends ModalRegistry>(
  _state: ModalState<R>,
  action: Action<R>,
): ModalState<R> {
  if (action.type === "close") {
    return { kind: null, payload: null } as ModalState<R>;
  }
  return { kind: action.kind, payload: action.payload } as ModalState<R>;
}

const INITIAL: ModalState<ModalRegistry> = { kind: null, payload: null };

export interface ModalApi<R extends ModalRegistry> {
  state: ModalState<R>;
  /** Открыть модалку. Если у неё нет payload — второй аргумент опционален. */
  open: <K extends keyof R>(
    kind: K,
    ...args: R[K] extends undefined ? [] : [R[K]]
  ) => void;
  close: () => void;
  /** Проверка с type-narrowing: если is("close") → state.payload типизирован. */
  is: <K extends keyof R>(
    kind: K,
  ) => boolean;
}

export function useModalState<R extends ModalRegistry>(): ModalApi<R> {
  const [state, dispatch] = useReducer(
    reducer as React.Reducer<ModalState<R>, Action<R>>,
    INITIAL as ModalState<R>,
  );

  const open = useCallback(
    <K extends keyof R>(
      kind: K,
      ...args: R[K] extends undefined ? [] : [R[K]]
    ) => {
      dispatch({
        type: "open",
        kind,
        payload: (args[0] ?? undefined) as R[keyof R],
      });
    },
    [],
  );

  const close = useCallback(() => dispatch({ type: "close" }), []);

  const is = useCallback(
    <K extends keyof R>(kind: K) => state.kind === kind,
    [state.kind],
  );

  return { state, open, close, is };
}
