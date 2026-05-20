import type { Metadata } from "next";
import { Cormorant, Fraunces, Inter, JetBrains_Mono, Manrope } from "next/font/google";
import "./globals.css";
import { LanguageProvider } from "@/i18n/LanguageContext";
import { SettingsProvider } from "@/contexts/SettingsContext";
import { AuthProvider } from "@/contexts/AuthContext";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { QueryProvider } from "@/lib/QueryProvider";
import { CookieConsent } from "@/components/CookieConsent";

// Fraunces: Latin/Latin-ext editorial display — axes opsz/SOFT/WONK
// No Cyrillic subset exists for Fraunces on Google Fonts
const fraunces = Fraunces({
  subsets: ["latin", "latin-ext"],
  variable: "--font-serif",
  axes: ["opsz", "SOFT", "WONK"],
  weight: "variable",
  style: ["normal", "italic"],
  display: "swap",
});

// Cormorant: Cyrillic companion serif — old-style humanist, harmonizes with Fraunces
// Used as Cyrillic fallback via --font-serif-cyr CSS variable in the font-family stack
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

// Manrope: Bloomberg-style display sans — max weight 800 (no 900 in Google Fonts subset)
const manrope = Manrope({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-display",
  weight: ["500", "700", "800"],
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
    <html lang="ru" className={`${fraunces.variable} ${cormorant.variable} ${inter.variable} ${geistMono.variable} ${manrope.variable}`} suppressHydrationWarning>
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
