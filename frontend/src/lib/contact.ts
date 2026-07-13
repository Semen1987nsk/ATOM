// Единый обслуживаемый адрес поддержки. Домен согласован с бизнес-решением
// (empirik.io оставлен осознанно до регистрации polistata.ru). ENV-override для прод.
export const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL || 'support@empirik.io';
export const SUPPORT_TELEGRAM = 'https://t.me/empirik_support_bot';
