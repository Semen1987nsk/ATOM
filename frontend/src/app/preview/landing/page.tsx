/**
 * Preview-route for the editorial Landing — direct SSR без auth-context.
 * Используется во время Phase 3–5 rebrand-сессии для скриншот-итерации
 * через chrome-devtools / playwright MCP. Удалить после Phase 5 verify.
 */

import { Landing } from "@/components/landing/Landing";

export default function LandingPreview() {
  return <Landing />;
}
