import type { Metadata } from "next";
import { Cormorant, Inter, JetBrains_Mono, Manrope } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";
import { LanguageProvider } from "@/i18n/LanguageContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { ToastProvider } from "@/contexts/ToastContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryProvider } from "@/lib/QueryProvider";
import { CookieConsent } from "@/components/CookieConsent";

// Cormorant: editorial serif (Cyrillic + Latin) для цитат и заголовков.
// Заменил Fraunces (Latin-only, ~150KB) — видимый serif-текст кириллический,
// который Fraunces всё равно не покрывал. globals.css алиасит
// --font-serif → --font-serif-cyr, существующие стеки работают без правок.
const cormorant = Cormorant({
  subsets: ["cyrillic", "cyrillic-ext", "latin"],
  variable: "--font-serif-cyr",
  weight: "variable",
  style: ["normal", "italic"],
  display: "swap",
});

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-sans",
  weight: ["400", "500", "600"],
  display: "swap",
});

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});

// Manrope: Bloomberg-style display sans — только 700 (CTA) и 800
// (H1/H2/числа), 500 выгружен ради веса бандла.
const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  variable: "--font-display",
  weight: ["700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Эмпирик — журнал торговых сделок | Торгуй по данным, не по догадкам.",
  description: "Журнал торговых сделок для активных трейдеров Московской биржи. Optimal f, SQN, MAE/MFE, Trade Replay. Каждая сделка — гипотеза. Данные выносят вердикт.",
  icons: {
    icon: [
      { url: "/landing/favicon-empirik.svg", type: "image/svg+xml" },
    ],
  },
  openGraph: {
    title: "Эмпирик — журнал торговых сделок",
    description: "Каждая сделка — гипотеза. Данные выносят вердикт.",
    url: "https://empirik.io",
    siteName: "Эмпирик",
    images: [{ url: "/landing/og-image-empirik.png", width: 1200, height: 630 }],
    locale: "ru_RU",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Эмпирик — журнал сделок",
    description: "Сигнал из шума.",
    images: ["/landing/og-image-empirik.png"],
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // SEC-14: nonce приходит из `src/middleware.ts`, который выставляет
  // его в request header через NextResponse.next({request:{headers}}).
  // <meta property="csp-nonce"> читает Sentry-loader (CDN) и любые сторонние
  // скрипты, которые хотят соблюдать CSP без явного nonce-prop.
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html
      lang="ru"
      className={`${cormorant.variable} ${inter.variable} ${jetbrainsMono.variable} ${manrope.variable}`}
      suppressHydrationWarning
    >
      <head>
        {nonce ? <meta property="csp-nonce" content={nonce} /> : null}
      </head>
      <body className="antialiased">
        <ErrorBoundary>
          <QueryProvider>
            <AuthProvider>
              <LanguageProvider>
                <SettingsProvider>
                  <ToastProvider>
                    {children}
                    <CookieConsent />
                  </ToastProvider>
                </SettingsProvider>
              </LanguageProvider>
            </AuthProvider>
          </QueryProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
