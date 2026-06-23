export type LedgerEntry = {
  pre: string;
  mark: string; // акцентный (оранжевый) фрагмент строки журнала
  post: string;
};

export type SimpleFactItem = {
  caption: string;
  heading: string;
  body: string;
  ledger: LedgerEntry; // иллюстративная «строка журнала» (демо-образец, не статистика)
};

export const SIMPLE_FACT_EYEBROW: string = "Раздел 00 — Сам факт записи";
export const SIMPLE_FACT_HEADING: string = "Сам факт записи уже меняет торговлю.";

export const SIMPLE_FACT_ITEMS: SimpleFactItem[] = [
  {
    caption: "01",
    heading: "Ты видишь сделки",
    body: "Память врёт. Запись — нет.",
    ledger: { pre: "12.06 · SBER · ", mark: "+1.8%", post: " · записано" },
  },
  {
    caption: "02",
    heading: "Ты признаёшь ошибки",
    body: "Цифра не спорит и не оправдывается.",
    ledger: { pre: "вход против тренда · ", mark: "4-й раз за месяц", post: "" },
  },
  {
    caption: "03",
    heading: "Ты растёшь от себя",
    body: "Не с рынком — с собой, квартал к кварталу.",
    ledger: { pre: "Q2 → Q3 · дисциплина ", mark: "↑", post: "" },
  },
];

export const SIMPLE_FACT_BRIDGE: string =
  "Метрики, MAE/MFE и AI — уже сверху. Но половину пользы даёт сам факт записи.";
