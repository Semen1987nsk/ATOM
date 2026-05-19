export type Champion = {
  slug: string;
  firstName: string;
  lastName: string;
  originalName?: string;
  birthYear: number;
  deathYear?: number;
  bio: string;          // ≤60 words — filled in Task 10
  quote: string;        // verbatim — filled in Task 10
  source: string;       // filled in Task 10
  wikipediaUrl: string; // for sameAs JSON-LD (used in Task 18)
  portraitSrc: string;
};

export const CHAMPIONS_LEDE: string =
  "Запись сделок — не изобретение SaaS-эпохи. Эти шестеро вели её на телеграммах, жёлтых блокнотах, рукописных колонках и электронных таблицах — от 1900-х до сегодня. Оставили в книгах формулу: что записано, то измерено.";

export const CHAMPIONS: Champion[] = [
  {
    slug: "livermore",
    firstName: "Джесси",
    lastName: "Ливермор",
    originalName: "Jesse Livermore",
    birthYear: 1877,
    deathYear: 1940,
    bio: "Американский биржевой спекулянт. Начинал в 14 лет в брокерской конторе Бостона. С 15 лет торговал в бакет-шопах. Заработал состояние на коротких позициях перед крахом 1929. Трижды банкротился. С подростковых лет вёл рукописную записную книжку — заносил цены акций и собственные прогнозы, перечитывал и сверял с фактом. Метод записи цен в связке со временем формализовал в книге 1940 года.",
    quote:
      "Я так увлёкся своей игрой и так хотел предугадывать движения всех активных акций, что завёл маленькую книжку. Записывал в неё свои наблюдения.",
    source: "«Reminiscences of a Stock Operator», Edwin Lefèvre, 1923, глава 1",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Ливермор,_Джесси",
    portraitSrc: "/landing/champions/livermore.svg",
  },
  {
    slug: "darvas",
    firstName: "Николас",
    lastName: "Дарвас",
    originalName: "Nicolas Darvas",
    birthYear: 1920,
    deathYear: 1977,
    bio: "Венгерский танцор и самоучка-трейдер. Бежал из Венгрии в 1943. Гастролировал с труппой по миру и торговал американскими акциями. За 18 месяцев 1957—1958 превратил $36 000 в $2 450 000. Изобрёл «Box Theory» — пробой ценового канала. Получал ежедневные кодированные телеграммы с ценами закрытия от Токио до Калькутты. Вечерами вписывал цифры от руки и решал, пробила ли акция верхнюю границу.",
    quote:
      "Даже в таких удалённых местах, как Кашмир и Непал, где Дарвас выступал на гастролях, ежедневная телеграмма исправно приходила. В ней — цены закрытия Уолл-стрит по его акциям.",
    source:
      "«How I Made $2,000,000 in the Stock Market», Nicolas Darvas, 1960, глава 5 «Cables Round the World»",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Дарвас,_Николас",
    portraitSrc: "/landing/champions/darvas.svg",
  },
  {
    slug: "minervini",
    firstName: "Марк",
    lastName: "Минервини",
    originalName: "Mark Minervini",
    birthYear: 1965,
    bio: "Американский трейдер, родился 22.01.1965. Бросил школу в 8 классе. С 1983 торгует акциями. В 1997 выиграл U.S. Investing Championship с +155%, в 2021 побил рекорд с +334,8%. Автор «Think & Trade Like a Champion» (2016). После каждой сделки заполняет post-trade spreadsheet: процент позиции, причина входа, уровень стопа, результат в R. Раз в квартал агрегирует и сверяет план с фактом.",
    quote: "Самая ценная информация о вашей торговле — это сама ваша торговля.",
    source:
      "«Think & Trade Like a Champion», Mark Minervini, 2016, глава «Post-Analysis: The Difference Between Champions and Amateurs»",
    wikipediaUrl: "https://cmtassociation.org/presenter/mark-minervini/",
    portraitSrc: "/landing/champions/minervini.svg",
  },
  {
    slug: "tudor-jones",
    firstName: "Пол",
    lastName: "Тюдор Джонс",
    originalName: "Paul Tudor Jones",
    birthYear: 1954,
    bio: "Американский хедж-фонд-менеджер, родился 28.09.1954 в Мемфисе. Основал Tudor Investment Corporation в 1980. Предсказал крах 1987 — короткие позиции принесли $100 млн в «Чёрный понедельник». Сооснователь Robin Hood Foundation (1988). Пишет от руки на жёлтых legal pads. Каждое утро перед открытием набрасывает play-by-play предполагаемого движения: что будет, если S&P пробьёт X, если облигации упадут до Y. Стопы фиксирует до входа.",
    quote:
      "У меня есть ментальный стоп. Если цена доходит до этого числа — я выхожу при любом раскладе.",
    source:
      "«Market Wizards: Interviews with Top Traders», Jack D. Schwager, 1989, глава «The Art of Aggressive Trading»",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Paul_Tudor_Jones",
    portraitSrc: "/landing/champions/tudor-jones.svg",
  },
  {
    slug: "elder",
    firstName: "Александр",
    lastName: "Элдер",
    originalName: "Alexander Elder",
    birthYear: 1950,
    bio: "Родился в Ленинграде в 1950. Вырос в Эстонии, закончил мединститут в Тарту. В 1974 бежал из СССР — получил убежище в США. Психиатр, преподавал в Колумбийском университете. Автор «Trading for a Living» (1993) — глава об учёте сделок. Ведёт три журнала: equity curve, сделки построчно и уроки. Скриншот графика на момент входа — обязательно.",
    quote:
      "Покажите мне трейдера с хорошими записями — и я покажу вам хорошего трейдера.",
    source:
      "«Come Into My Trading Room», Alexander Elder, 2002, глава «Record-Keeping»",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Элдер,_Александр",
    portraitSrc: "/landing/champions/elder.svg",
  },
  {
    slug: "raschke",
    firstName: "Линда",
    lastName: "Брэдфорд Рашке",
    originalName: "Linda Bradford Raschke",
    birthYear: 1959,
    bio: "Американская трейдер, родилась в 1959 в Пасадене. Диплом Occidental College по экономике и музыкальной композиции (1980). С 1981 — market maker по опционам, затем futures-трейдер. Основала LBRGroup. Соавтор «Street Smarts» (1995) и автор «Trading Sardines» (2018). Каждый день от руки записывает показания индикаторов и цены закрытия по 24+ фьючерсным рынкам. Вечером размечает графики на следующий день: сетапы, conditional rules входа.",
    quote:
      "Я научилась большему, размечая сигналы прямо на графиках, изучая случаи, когда сигнал не сработал, ища вторичные подтверждающие признаки и записывая моря данных вручную.",
    source:
      "«Trading Sardines: Lessons in the Markets from a Lifelong Trader», Linda Bradford Raschke, 2018, Daughters Publishing",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Linda_Bradford_Raschke",
    portraitSrc: "/landing/champions/raschke.svg",
  },
];
