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

export const CHAMPIONS_LEDE: string = ""; // 1-2 sentences — filled in Task 10

export const CHAMPIONS: Champion[] = [
  {
    slug: "livermore",
    firstName: "Джесси",
    lastName: "Ливермор",
    originalName: "Jesse Livermore",
    birthYear: 1877,
    deathYear: 1940,
    bio: "",
    quote: "",
    source: "",
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
    bio: "",
    quote: "",
    source: "",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Дарвас,_Николас",
    portraitSrc: "/landing/champions/darvas.svg",
  },
  {
    slug: "minervini",
    firstName: "Марк",
    lastName: "Минервини",
    originalName: "Mark Minervini",
    birthYear: 1965,
    bio: "",
    quote: "",
    source: "",
    wikipediaUrl: "https://cmtassociation.org/presenter/mark-minervini/",
    portraitSrc: "/landing/champions/minervini.svg",
  },
  {
    slug: "tudor-jones",
    firstName: "Пол",
    lastName: "Тюдор Джонс",
    originalName: "Paul Tudor Jones",
    birthYear: 1954,
    bio: "",
    quote: "",
    source: "",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Paul_Tudor_Jones",
    portraitSrc: "/landing/champions/tudor-jones.svg",
  },
  {
    slug: "elder",
    firstName: "Александр",
    lastName: "Элдер",
    originalName: "Alexander Elder",
    birthYear: 1950,
    bio: "",
    quote: "",
    source: "",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Элдер,_Александр",
    portraitSrc: "/landing/champions/elder.svg",
  },
  {
    slug: "raschke",
    firstName: "Линда",
    lastName: "Брэдфорд Рашке",
    originalName: "Linda Bradford Raschke",
    birthYear: 1959,
    bio: "",
    quote: "",
    source: "",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Linda_Bradford_Raschke",
    portraitSrc: "/landing/champions/raschke.svg",
  },
];
