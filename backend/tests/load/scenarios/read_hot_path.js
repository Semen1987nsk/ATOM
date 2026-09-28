// backend/tests/load/scenarios/read_hot_path.js
// Sprint 3 PERF-load: mix хороших read-эндпойнтов под ramping VU.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.AUTH_TOKEN;

if (!TOKEN) {
  throw new Error('AUTH_TOKEN env-var required');
}

const statsLatency = new Trend('stats_latency', true);
const tradesLatency = new Trend('trades_latency', true);
const positionsLatency = new Trend('positions_latency', true);
const marketLatency = new Trend('market_latency', true);
const errorRate = new Rate('errors');
const rateLimited = new Counter('rate_limited');

export const options = {
  scenarios: {
    read_mix: {
      executor: 'ramping-vus',
      startVUs: 10,
      stages: [
        { duration: '1m', target: 100 },
        { duration: '3m', target: 500 },
        { duration: '5m', target: 500 },
        { duration: '1m', target: 0 },
      ],
    },
  },
  thresholds: {
    'stats_latency': ['p(95)<800'],
    'trades_latency': ['p(95)<400'],
    'positions_latency': ['p(95)<500'],
    'market_latency': ['p(95)<600'],
    'errors': ['rate<0.01'],
  },
};

const headers = { Authorization: `Bearer ${TOKEN}` };

export default function () {
  const r1 = http.get(`${BASE}/stats/`, { headers });
  statsLatency.add(r1.timings.duration);
  errorRate.add(r1.status >= 400);
  if (r1.status === 429) rateLimited.add(1);
  check(r1, { 'stats 200': (r) => r.status === 200 });

  const r2 = http.get(`${BASE}/trades/?limit=100`, { headers });
  tradesLatency.add(r2.timings.duration);
  errorRate.add(r2.status >= 400);
  if (r2.status === 429) rateLimited.add(1);

  const r3 = http.get(`${BASE}/trades/positions?limit=50&status=open`, { headers });
  positionsLatency.add(r3.timings.duration);
  errorRate.add(r3.status >= 400);
  if (r3.status === 429) rateLimited.add(1);

  const r4 = http.get(`${BASE}/market/prices?tickers=SBER,GAZP,LKOH`, { headers });
  marketLatency.add(r4.timings.duration);
  errorRate.add(r4.status >= 400);
  if (r4.status === 429) rateLimited.add(1);

  sleep(Math.random() * 2 + 1); // 1–3s think-time
}
