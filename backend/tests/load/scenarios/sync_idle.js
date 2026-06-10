// backend/tests/load/scenarios/sync_idle.js
// Sprint 3: 500 idle VU, держит keep-alive коннекции, без активных запросов.
// Проверка пула коннекций и memory baseline.

import http from 'k6/http';
import { sleep } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:8000';
const TOKEN = __ENV.AUTH_TOKEN;

export const options = {
  vus: 500,
  duration: '5m',
};

const headers = { Authorization: `Bearer ${TOKEN}` };

export default function () {
  // Лёгкий heartbeat — /health (или /ready), чтобы коннекция жила.
  http.get(`${BASE}/health`);
  sleep(30); // редко
}
