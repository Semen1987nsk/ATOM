"use client";

import { useEffect, useState } from "react";
import { useInView } from "@/hooks/useInView";

export type CountUpProps = {
  to: number;
  durationMs?: number;
  suffix?: string;
  prefix?: string;
  decimals?: number;
  className?: string;
};

export function CountUp({ to, durationMs = 1500, suffix = "", prefix = "", decimals = 0, className }: CountUpProps) {
  const { ref, inView } = useInView<HTMLSpanElement>({ rootMargin: "0px 0px -100px 0px", once: true });
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      const t = setTimeout(() => setValue(to), 0);
      return () => clearTimeout(t);
    }
    let raf = 0;
    const start = performance.now();
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    const step = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(elapsed / durationMs, 1);
      setValue(to * ease(t));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, durationMs]);

  const formatted = decimals > 0 ? value.toFixed(decimals) : Math.round(value).toString();
  return (
    <span ref={ref} className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
