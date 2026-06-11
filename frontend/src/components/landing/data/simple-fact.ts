export type SimpleFactItem = {
  caption: string;
  heading: string;
  body: string;
};

export const SIMPLE_FACT_EYEBROW: string = "Раздел 00 — Сам факт записи";
export const SIMPLE_FACT_HEADING: string = "Дневник до всяких метрик.";

export const SIMPLE_FACT_ITEMS: SimpleFactItem[] = [
  {
    caption: "01",
    heading: "Ты видишь сделки",
    body: "Не помнишь — видишь. Память врёт. Запись — нет.",
  },
  {
    caption: "02",
    heading: "Ты признаёшь ошибки",
    body: "Не оправдываешь — признаёшь. Цифра не спорит.",
  },
  {
    caption: "03",
    heading: "Ты сравниваешь себя с собой",
    body: "Не с рынком — с собой. Квартал к кварталу.",
  },
];

export const SIMPLE_FACT_BRIDGE: string =
  "Это всё, что нужно. Метрики и алгоритмы — уже сверху.";
