import type { Metadata } from "next";
import { Cormorant, Inter, JetBrains_Mono, Manrope } from "next/font/google";
import "./globals.css";
import { LanguageProvider } from "@/i18n/LanguageContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryProvider } from "@/lib/QueryProvider";
import { CookieConsent } from "@/components/CookieConsent";

// Cormorant: editorial serif (Cyrillic + Latin) for cited quotes.
// Replaced Fraunces (Latin-only, 3-axis variable, ~150KB) — on this RU page
// the visible quote text is Cyrillic, which Fraunces could not render anyway,
// so Cormorant carries the serif role alone. globals.css aliases
// --font-serif → --font-serif-cyr so existing stacks resolve to Cormorant.
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

const geistMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});

// Manrope: Bloomberg-style display sans — max weight 800 (no 900 in Google Fonts subset).
// Only 700 (CTA) and 800 (H1/H2/numbers/names) are used — 500 dropped to trim weight.
const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  variable: "--font-display",
  weight: ["700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "МААТТ — журнал торговых сделок | Точно. Чисто. Честно.",
  description: "Журнал торговых сделок для активных трейдеров Московской биржи. Optimal f, SQN, MAE/MFE, Trade Replay. Каждая сделка измерена. Каждое решение взвешено.",
  icons: {
    icon: [
      { url: "/landing/favicon-feather.svg", type: "image/svg+xml" },
      { url: "/landing/favicon-feather-32.png", sizes: "32x32", type: "image/png" },
    ],
  },
  openGraph: {
    title: "МААТТ — журнал торговых сделок",
    description: "Каждая сделка измерена. Каждое решение взвешено.",
    url: "https://maatt.ru",
    siteName: "МААТТ",
    images: [{ url: "/landing/og-image-maatt.png", width: 1200, height: 630 }],
    locale: "ru_RU",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "МААТТ — журнал сделок",
    description: "Точно. Чисто. Честно.",
    images: ["/landing/og-image-maatt.png"],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className={`${cormorant.variable} ${inter.variable} ${geistMono.variable} ${manrope.variable}`} suppressHydrationWarning>
      <body className="antialiased">
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
