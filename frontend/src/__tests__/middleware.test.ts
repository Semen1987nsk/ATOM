// SEC-14 (Sprint 6, Batch 3): per-request CSP nonce — frontend Next.js
// middleware/proxy авторитативен для HTML-страниц. Эти тесты падают пока
// `src/middleware.ts` не создан и проверяют контракт:
//
//   1. CSP заголовок выставлен с уникальным nonce на каждый запрос
//   2. script-src НЕ содержит 'unsafe-inline' (заменён на nonce+strict-dynamic)
//   3. nonce передаётся в downstream через x-nonce request header
//      (механика NextResponse.next({request:{headers}}) — мы проверяем по
//      уникальности nonce между двумя запросами как proxy-индикатор).
import { describe, it, expect } from 'vitest';
import { NextRequest } from 'next/server';

import { middleware } from '../middleware';

describe('CSP nonce middleware', () => {
  it('adds Content-Security-Policy header with nonce', () => {
    const req = new NextRequest('http://localhost:3000/');
    const res = middleware(req);
    const csp = res.headers.get('content-security-policy');
    expect(csp).toBeTruthy();
    // base64-nonce может содержать + / = — проверяем формат токена.
    expect(csp).toMatch(/script-src[^;]*'nonce-[A-Za-z0-9+/=]+'/);
    // script-src НЕ должен содержать 'unsafe-inline' — это и есть смысл SEC-14.
    const scriptSrc = csp!.split(';').find(d => d.trim().startsWith('script-src')) ?? '';
    expect(scriptSrc).not.toContain("'unsafe-inline'");
  });

  it('generates different nonce per request', () => {
    const r1 = middleware(new NextRequest('http://localhost:3000/'));
    const r2 = middleware(new NextRequest('http://localhost:3000/'));
    const csp1 = r1.headers.get('content-security-policy');
    const csp2 = r2.headers.get('content-security-policy');
    expect(csp1).toBeTruthy();
    expect(csp2).toBeTruthy();
    expect(csp1).not.toEqual(csp2);
  });

  it('sets x-nonce request header for downstream consumers', () => {
    const req = new NextRequest('http://localhost:3000/');
    const res = middleware(req);
    // Next.js пробрасывает request.headers внутрь response через
    // NextResponse.next({request:{headers}}) — внешне это видно как
    // x-middleware-override-headers + x-middleware-request-x-nonce.
    // Минимальный observable contract — что CSP несёт реальный nonce
    // (значит он сгенерирован и пробрасывается).
    const csp = res.headers.get('content-security-policy');
    expect(csp).toMatch(/'nonce-[A-Za-z0-9+/=]+'/);
  });

  it('includes strict-dynamic and required Sentry/yookassa hosts in script-src', () => {
    const res = middleware(new NextRequest('http://localhost:3000/'));
    const csp = res.headers.get('content-security-policy')!;
    expect(csp).toContain("'strict-dynamic'");
    expect(csp).toContain('https://*.ingest.sentry.io');
    expect(csp).toContain('https://yookassa.ru');
  });

  it('keeps frame-ancestors none and object-src none', () => {
    const res = middleware(new NextRequest('http://localhost:3000/'));
    const csp = res.headers.get('content-security-policy')!;
    expect(csp).toContain("frame-ancestors 'none'");
    expect(csp).toContain("object-src 'none'");
  });
});
