import type { Metadata } from "next";
import { Geist, Geist_Mono, Fraunces } from "next/font/google";
import { headers } from "next/headers";
import "./globals.css";
import { LanguageProvider } from "@/i18n/LanguageContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryProvider } from "@/lib/QueryProvider";
import { CookieConsent } from "@/components/CookieConsent";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin", "cyrillic"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Editorial serif для headlines / lede / pull-quotes.
// NB: Google-шрифт Fraunces не имеет cyrillic-сабсета — кириллица в этих
// местах рендерится фолбэком. Выбор serif с кириллицей — см. дизайн-трек.
// ADR-0006 (editorial-financial-rebrand), design-system.md v3.
const fraunces = Fraunces({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Эмпирик",
  description: "Система торговой аналитики на базе ИИ",
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
    <html lang="ru" suppressHydrationWarning>
      <head>
        {nonce ? <meta property="csp-nonce" content={nonce} /> : null}
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} ${fraunces.variable} antialiased`}
      >
        <ErrorBoundary>
          <QueryProvider>
            <AuthProvider>
              <LanguageProvider>
                <SettingsProvider>
                  {children}
                  <CookieConsent />
                </SettingsProvider>
              </LanguageProvider>
            </AuthProvider>
          </QueryProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
