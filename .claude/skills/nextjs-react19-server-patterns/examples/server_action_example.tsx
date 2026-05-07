/**
 * Пример: Server Action для добавления тега к сделке.
 *
 * Контекст Eqio:
 *   - Сейчас тег добавляется через client-side fetch к FastAPI:
 *     await api.post(`/trades/${id}/tags`, { body: { tag } });
 *   - Минусы текущего подхода: ручной loading state, нет revalidate, не работает без JS.
 *
 * Этот пример показывает как переписать через Server Action.
 *
 * Файлы:
 *   - src/actions/tags.ts                          (Server Action, 'use server')
 *   - src/lib/serverApiClient.ts                   (server-only fetch к FastAPI)
 *   - src/components/dashboard/TagAdder.tsx        (Client UI: form + useActionState)
 *
 * Что использовано:
 *   - 'use server' директива
 *   - Zod для валидации input
 *   - cookies() из next/headers (httpOnly cookie проброс к FastAPI)
 *   - revalidateTag после успеха
 *   - useActionState для pending/error state
 *   - useOptimistic для мгновенного UI-апдейта
 *   - <form action={...}> — нативная интеграция React 19
 */

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 1: src/lib/serverApiClient.ts
// Server-only клиент к FastAPI. Параллель к существующему apiClient.ts,
// но читает cookies через next/headers а не document.cookie.
// ═════════════════════════════════════════════════════════════════

import { cookies } from 'next/headers';

const API_BASE = process.env.API_BASE_URL ?? 'http://localhost:8003';

interface ServerApiOptions {
  body?: unknown;
  cache?: RequestCache;
  next?: NextFetchRequestConfig;
}

class ServerApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly detail: string,
  ) {
    super(detail);
    this.name = 'ServerApiError';
  }
}

async function serverRequest<T>(
  method: string,
  path: string,
  options: ServerApiOptions = {},
): Promise<T> {
  const cookieStore = await cookies();
  const cookieHeader = cookieStore
    .getAll()
    .map((c) => `${c.name}=${c.value}`)
    .join('; ');

  const csrfToken = cookieStore.get('atom_csrf_token')?.value;
  const isUnsafe = !['GET', 'HEAD', 'OPTIONS'].includes(method);

  const headers: Record<string, string> = {
    cookie: cookieHeader,
  };
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (isUnsafe && csrfToken) headers['X-CSRF-Token'] = csrfToken;

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: options.cache,
    next: options.next,
  });

  if (!res.ok) {
    const data = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new ServerApiError(res.status, data.detail ?? `HTTP ${res.status}`);
  }

  const text = await res.text();
  if (!text) return null as T;
  return JSON.parse(text) as T;
}

export const serverApi = {
  get: <T = unknown>(path: string, opts?: ServerApiOptions) => serverRequest<T>('GET', path, opts),
  post: <T = unknown>(path: string, opts?: ServerApiOptions) => serverRequest<T>('POST', path, opts),
  patch: <T = unknown>(path: string, opts?: ServerApiOptions) => serverRequest<T>('PATCH', path, opts),
  delete: <T = unknown>(path: string, opts?: ServerApiOptions) => serverRequest<T>('DELETE', path, opts),
};

export { ServerApiError };

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 2: src/actions/tags.ts
// 'use server' — модуль-уровневая директива. Все экспорты — Server Actions.
// ═════════════════════════════════════════════════════════════════

'use server';

import { z } from 'zod';
import { revalidateTag } from 'next/cache';
// import { serverApi, ServerApiError } from '@/lib/serverApiClient';

export type ActionState =
  | { ok: true }
  | { ok: false; error: string; fieldErrors?: Partial<Record<'tag' | 'tradeId', string>> };

const AddTagSchema = z.object({
  tradeId: z.coerce.number().int().positive(),
  tag: z
    .string()
    .trim()
    .min(1, 'Тег не может быть пустым')
    .max(50, 'Максимум 50 символов')
    .regex(/^[a-zA-Zа-яА-ЯёЁ0-9_\-\s]+$/, 'Недопустимые символы'),
});

export async function addTagToTradeAction(
  _prevState: ActionState,
  formData: FormData,
): Promise<ActionState> {
  const parsed = AddTagSchema.safeParse({
    tradeId: formData.get('tradeId'),
    tag: formData.get('tag'),
  });

  if (!parsed.success) {
    const fieldErrors: NonNullable<ActionState extends { fieldErrors?: infer F } ? F : never> = {};
    for (const issue of parsed.error.issues) {
      const key = issue.path[0];
      if (key === 'tag' || key === 'tradeId') fieldErrors[key] = issue.message;
    }
    return {
      ok: false,
      error: parsed.error.issues[0]?.message ?? 'Ошибка валидации',
      fieldErrors,
    };
  }

  try {
    await serverApi.post(`/trades/${parsed.data.tradeId}/tags`, {
      body: { tag: parsed.data.tag },
    });
    revalidateTag('trades-list');
    revalidateTag(`trade:${parsed.data.tradeId}`);
    return { ok: true };
  } catch (e) {
    if (e instanceof ServerApiError) {
      if (e.status === 409) return { ok: false, error: 'Этот тег уже добавлен' };
      if (e.status === 401) return { ok: false, error: 'Сессия истекла, войдите снова' };
    }
    return { ok: false, error: e instanceof Error ? e.message : 'Не удалось добавить тег' };
  }
}

export async function removeTagFromTradeAction(
  tradeId: number,
  tag: string,
): Promise<ActionState> {
  // Альтернативный сигнатур: вызов как обычной функции, не через FormData.
  // Удобно для onClick-кнопок без формы.
  try {
    await serverApi.delete(`/trades/${tradeId}/tags/${encodeURIComponent(tag)}`);
    revalidateTag('trades-list');
    revalidateTag(`trade:${tradeId}`);
    return { ok: true };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : 'Не удалось удалить тег' };
  }
}

// ═════════════════════════════════════════════════════════════════
// ФАЙЛ 3: src/components/dashboard/TagAdder.tsx
// Client-компонент. Форма + оптимистичный UI.
// ═════════════════════════════════════════════════════════════════

'use client';

import { useActionState, useOptimistic, useRef, startTransition } from 'react';
import { Tag, X, Loader2 } from 'lucide-react';
// import { addTagToTradeAction, removeTagFromTradeAction, type ActionState } from '@/actions/tags';

interface TagAdderProps {
  tradeId: number;
  initialTags: string[];
}

const initialState: ActionState = { ok: true };

export function TagAdder({ tradeId, initialTags }: TagAdderProps) {
  const formRef = useRef<HTMLFormElement>(null);

  // useActionState — pending state из коробки, без useState/setLoading
  const [state, formAction, isPending] = useActionState(addTagToTradeAction, initialState);

  // Оптимистичный список тегов: показываем добавленный тег мгновенно,
  // не дожидаясь возврата с сервера.
  const [optimisticTags, addOptimisticTag] = useOptimistic(
    initialTags,
    (current: string[], next: { type: 'add' | 'remove'; tag: string }) =>
      next.type === 'add'
        ? [...current, next.tag]
        : current.filter((t) => t !== next.tag),
  );

  const handleSubmit = (formData: FormData) => {
    const tag = String(formData.get('tag') ?? '').trim();
    if (!tag) return;

    // useOptimistic должен вызываться внутри transition (чтобы оптимистичный
    // апдейт не блокировал input). startTransition оборачивает и оптимистичную
    // мутацию, и сабмит формы.
    startTransition(() => {
      addOptimisticTag({ type: 'add', tag });
      formAction(formData);
    });
    formRef.current?.reset();
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        {optimisticTags.map((tag) => (
          <TagChip
            key={tag}
            tag={tag}
            onRemove={() => {
              startTransition(async () => {
                addOptimisticTag({ type: 'remove', tag });
                await removeTagFromTradeAction(tradeId, tag);
              });
            }}
          />
        ))}
        {optimisticTags.length === 0 && (
          <span className="text-[12px] text-[var(--text-tertiary)]">Тегов пока нет</span>
        )}
      </div>

      <form ref={formRef} action={handleSubmit} className="flex items-center gap-2">
        <input type="hidden" name="tradeId" value={tradeId} />
        <div className="relative flex-1">
          <Tag
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-tertiary)] pointer-events-none"
          />
          <input
            name="tag"
            placeholder="Добавить тег..."
            required
            disabled={isPending}
            maxLength={50}
            aria-invalid={state.ok === false && Boolean(state.fieldErrors?.tag)}
            className="w-full pl-9 pr-3 py-2 text-[13px] rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--surface-1)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/40 disabled:opacity-50"
          />
        </div>
        <button
          type="submit"
          disabled={isPending}
          className="px-3 py-2 text-[13px] font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] disabled:opacity-50 inline-flex items-center gap-1.5"
        >
          {isPending && <Loader2 size={13} className="animate-spin" />}
          Добавить
        </button>
      </form>

      {state.ok === false && (
        <div role="alert" className="text-[12px] text-[var(--danger)]">
          {state.error}
        </div>
      )}
    </div>
  );
}

function TagChip({ tag, onRemove }: { tag: string; onRemove: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-[var(--radius-pill)] bg-[var(--accent-soft)] text-[var(--accent)] text-[12px] font-medium">
      {tag}
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Удалить тег ${tag}`}
        className="hover:opacity-80"
      >
        <X size={11} />
      </button>
    </span>
  );
}

// ═════════════════════════════════════════════════════════════════
// ИСПОЛЬЗОВАНИЕ
// ═════════════════════════════════════════════════════════════════
//
// // app/trades/[id]/page.tsx (Server Component, async)
// export default async function TradePage({ params }: { params: Promise<{ id: string }> }) {
//   const { id } = await params;
//   const trade = await serverApi.get<Trade>(`/trades/${id}`, {
//     next: { tags: [`trade:${id}`] },
//   });
//   return (
//     <div>
//       <h1>{trade.symbol}</h1>
//       <TagAdder tradeId={trade.id} initialTags={trade.tags ?? []} />
//     </div>
//   );
// }
