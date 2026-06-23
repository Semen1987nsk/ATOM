export type Champion = {
  slug: string;
  firstName: string;
  lastName: string;
  originalName?: string;
  birthYear: number;
  deathYear?: number;
  bio: string;          // ≤60 words
  quote: string;        // verbatim / documented
  source: string;
  wikipediaUrl: string; // for sameAs JSON-LD
  portraitSrc: string;
};

export const CHAMPIONS_LEDE: string =
  "Запись сделок — не изобретение SaaS-эпохи. От рисовой биржи Сакаты XVIII века до жёлтых блокнотов Уолл-стрит лучшие трейдеры двух столетий вели её вручную: в телеграммах, рукописных колонках, электронных таблицах. И оставили в книгах одну формулу: что записано — то измеримо; что измеримо — тем можно управлять.";

export const CHAMPIONS_OUTRO: string =
  "Они выводили это годами — вручную, по вечерам, в блокнотах. Полистата ведёт тот же учёт за вас: MAE/MFE из свечей MOEX, R-кратность, паттерны входов и повторяющихся ошибок считаются сами, после каждой сделки. Дисциплина чемпионов — теперь по умолчанию.";

export const CHAMPIONS: Champion[] = [
  {
    slug: "homma",
    firstName: "Мунэхиса",
    lastName: "Хомма",
    originalName: "Munehisa Homma",
    birthYear: 1724,
    deathYear: 1803,
    bio: "Японский торговец рисом из Сакаты, «бог рынков» — родоначальник свечного анализа. Десятилетиями вёл рукописный учёт цен на бирже Додзима и держал цепочку сигнальщиков от Осаки до Сакаты, чтобы фиксировать котировки почти в реальном времени. Метод изложил в «The Fountain of Gold» (1755) — самой ранней известной книге о торговом учёте и психологии рынка.",
    quote:
      "Когда ты настроен оптимистично — оптимистичны и все вокруг; когда пессимистичен — пессимистичны и они.",
    source:
      "«The Fountain of Gold — The Three Monkey Record of Money», Munehisa Homma, 1755",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Honma_Munehisa",
    portraitSrc: "/landing/champions/homma.svg",
  },
  {
    slug: "livermore",
    firstName: "Джесси",
    lastName: "Ливермор",
    originalName: "Jesse Livermore",
    birthYear: 1877,
    deathYear: 1940,
    bio: "Американский биржевой спекулянт. Начинал в 14 лет в брокерской конторе Бостона, с 15 торговал в бакет-шопах. Сделал состояние на коротких позициях перед крахом 1929. С подростковых лет вёл рукописную записную книжку — заносил цены акций и собственные прогнозы, перечитывал и сверял с фактом. Свой метод записи цен формализовал в книге «How to Trade in Stocks» (1940).",
    quote:
      "Я так увлёкся своей игрой и так хотел предугадывать движения всех активных акций, что завёл маленькую книжку. Записывал в неё свои наблюдения.",
    source:
      "«Reminiscences of a Stock Operator», Edwin Lefèvre, 1923 (роман о Ливерморе), глава 1",
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
    bio: "Венгерский танцор и трейдер-самоучка. Гастролируя по миру, получал телеграммы с ценами закрытия Уолл-стрит и каждый раз записывал котировки от руки. Изобрёл «Box Theory» — пробой ценового канала. Его бестселлер 1960 года прославил дисциплину записи: фиксировать причину каждого убытка и не спорить с собственными цифрами.",
    quote:
      "У меня нет эго на бирже. Если я ошибся — признаю это сразу и быстро выхожу.",
    source:
      "«How I Made $2,000,000 in the Stock Market», Nicolas Darvas, 1960",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Дарвас,_Николас",
    portraitSrc: "/landing/champions/darvas.svg",
  },
  {
    slug: "minervini",
    firstName: "Марк",
    lastName: "Минервини",
    originalName: "Mark Minervini",
    birthYear: 1965,
    bio: "Американский трейдер, родился в 1965. Бросил школу в 8 классе. С 1983 торгует акциями. В 1997 выиграл U.S. Investing Championship с +155%, в 2021 побил рекорд с +334,8%. Автор «Think & Trade Like a Champion» (2016). После каждой сделки заполняет post-trade spreadsheet: процент позиции, причина входа, уровень стопа, результат в R. Раз в квартал агрегирует и сверяет план с фактом.",
    quote:
      "Ваша таблица сделок — не просто архив прошлых результатов. Это точный ориентир для следующих.",
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
    bio: "Американский управляющий хедж-фондом, родился в 1954 в Мемфисе. Основал Tudor Investment Corporation в 1980. Предсказал крах 1987 — фонд заработал около $100 млн за тот год на падении рынка. Сооснователь Robin Hood Foundation (1988). Каждый день заново проверяет каждую позицию «на ошибку» и заранее, до входа, фиксирует уровень риска и точку выхода.",
    quote:
      "Каждый день я исхожу из того, что все мои позиции ошибочны. Я заранее знаю, где будут мои точки риска.",
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
    bio: "Родился в Ленинграде в 1950. Вырос в Эстонии, закончил мединститут в Тарту. В начале 1970-х, в 23 года, бежал из СССР — сошёл с советского судна и получил убежище в США. Психиатр, преподавал в Колумбийском университете. Автор «Trading for a Living» (1993). Ведёт четыре вида записей: equity curve, сделки построчно, дневник и план на завтра. Скриншот графика на момент входа — обязательно.",
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
    bio: "Американская трейдер, родилась в 1959 в Пасадене. Диплом Occidental College по экономике и музыкальной композиции (1980). С 1981 — market maker по опционам, затем futures-трейдер. Основала LBRGroup. Соавтор «Street Smarts» (1995) и автор «Trading Sardines» (2018). Каждый день от руки записывает показания индикаторов и цены закрытия по десяткам фьючерсных рынков. Вечером размечает графики на следующий день: сетапы, conditional rules входа.",
    quote:
      "Я научилась большему, размечая сигналы прямо на графиках, изучая случаи, когда сигнал не сработал, ища вторичные подтверждающие признаки и записывая моря данных вручную.",
    source:
      "«Trading Sardines: Lessons in the Markets from a Lifelong Trader», Linda Bradford Raschke, 2018, Daughters Publishing",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Linda_Bradford_Raschke",
    portraitSrc: "/landing/champions/raschke.svg",
  },
];
