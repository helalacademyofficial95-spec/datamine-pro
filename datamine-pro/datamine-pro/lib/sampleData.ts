import type { Company, Country, Project, VerificationStatus } from "./types";

/**
 * SAMPLE DATA ONLY.
 * Every company below is generated from a fixed random seed so the demo looks the same on every
 * visit. Names, people, phone numbers, e-mails and web addresses are invented (the ".example"
 * domain is reserved and can never belong to a real website). No website was contacted.
 */

function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const rand = mulberry32(20261105);
const pick = <T,>(items: readonly T[]): T => items[Math.floor(rand() * items.length)];
const between = (min: number, max: number) => Math.floor(rand() * (max - min + 1)) + min;

const PREFIXES = [
  "Atelier", "Maison", "Groupe", "Studio", "Nordique", "Lumière", "Boréal", "Ardenne", "Meuse", "Alpin",
  "Vauban", "Cobalt", "Helios", "Orion", "Quartz", "Pivot", "Delta", "Rivage", "Cèdre", "Horizon",
];
const SECTORS = [
  "Logistique", "Conseil", "Énergie", "Textile", "Digital", "Bâtiment", "Agro", "Mobilité", "Santé",
  "Design", "Informatique", "Éditions", "Matériaux", "Voyages",
];
const SUFFIX: Record<Country, string[]> = {
  France: ["SAS", "SARL", "SA"],
  Belgium: ["SRL", "SA", "BV"],
  Luxembourg: ["S.à r.l.", "SA"],
  Other: ["Ltd", "LLC", "Inc."],
};
const FIRST = [
  "Camille", "Julien", "Élodie", "Thomas", "Sophie", "Nicolas", "Claire", "Antoine", "Margaux", "Lucas",
  "Inès", "Mathieu", "Léa", "Hugo", "Manon", "Pierre", "Chloé", "Maxime", "Sarah", "Olivier",
];
const LAST = [
  "Lambert", "Moreau", "Dupuis", "Girard", "Peeters", "Janssens", "Maes", "Weber", "Schmit", "Bernard",
  "Fontaine", "Renard", "Claes", "Hoffmann", "Muller", "Vidal", "Lefèvre", "Dubois", "Thiry", "Klein",
];
const PLACES: Record<Country, { city: string; zip: string }[]> = {
  France: [
    { city: "Lyon", zip: "69002" }, { city: "Lille", zip: "59000" }, { city: "Nantes", zip: "44000" },
    { city: "Strasbourg", zip: "67000" }, { city: "Bordeaux", zip: "33000" }, { city: "Paris", zip: "75011" },
  ],
  Belgium: [
    { city: "Bruxelles", zip: "1000" }, { city: "Liège", zip: "4000" }, { city: "Namur", zip: "5000" },
    { city: "Gand", zip: "9000" }, { city: "Anvers", zip: "2000" },
  ],
  Luxembourg: [
    { city: "Luxembourg", zip: "L-1219" }, { city: "Esch-sur-Alzette", zip: "L-4010" }, { city: "Differdange", zip: "L-4501" },
  ],
  Other: [{ city: "Other", zip: "00000" }],
};
const STREETS = ["rue de la Gare", "avenue des Arts", "rue du Commerce", "boulevard Voltaire", "rue des Tanneurs", "place du Marché", "rue Pasteur", "chemin du Moulin"];
const PHONE_PREFIX: Record<Country, string> = { France: "+33 1 99 00", Belgium: "+32 2 555", Luxembourg: "+352 27 99", Other: "+1 555 010" };

const slug = (s: string) =>
  s
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");

const two = () => String(between(0, 99)).padStart(2, "0");

/** Employee bands are weighted towards small companies, like a real market. */
function employeeCount(): number {
  const r = rand();
  if (r < 0.28) return between(1, 9);
  if (r < 0.5) return between(10, 19);
  if (r < 0.74) return between(20, 49);
  if (r < 0.88) return between(50, 99);
  return between(100, 249);
}

function buildCompanies(count: number): Company[] {
  const list: Company[] = [];
  const used = new Set<string>();
  const countries: Country[] = ["France", "France", "France", "Belgium", "Belgium", "Luxembourg"];
  while (list.length < count) {
    const country = pick(countries);
    const base = `${pick(PREFIXES)} ${pick(SECTORS)}`;
    if (used.has(base)) continue;
    used.add(base);
    const name = `${base} ${pick(SUFFIX[country])}`;
    const domain = `${slug(base)}.example`;
    const place = pick(PLACES[country]);
    const employees = employeeCount();
    const turnover = Math.round((employees * between(55, 230) * 1000) / 1000) * 1000;

    const emailVerified = rand() < 0.74;
    const phoneVerified = rand() < 0.62;
    const verification: VerificationStatus =
      emailVerified && phoneVerified ? "Verified" : emailVerified || phoneVerified ? "Partially verified" : "Unverified";
    const month = between(8, 10);
    const day = between(1, 28);

    list.push({
      id: `sample-${String(list.length + 1).padStart(3, "0")}`,
      name,
      director: `${pick(FIRST)} ${pick(LAST)}`,
      email: `contact@${domain}`,
      phone: `${PHONE_PREFIX[country]} ${two()} ${two()}`,
      employees,
      turnover,
      country,
      address: `${between(1, 120)} ${pick(STREETS)}, ${place.zip} ${place.city}`,
      website: `https://www.${domain}`,
      b2cWebsite: rand() < 0.55 ? `https://shop.${domain}` : null,
      emailVerified,
      phoneVerified,
      verification,
      origin: "sample",
      extractedAt: `2026-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
    });
  }
  return list;
}

export const SAMPLE_COMPANIES: Company[] = buildCompanies(72);

export const SAMPLE_PROJECTS: Project[] = [
  {
    id: "proj-sample-1",
    name: "Benelux logistics directory",
    sources: ["https://directory-logistics.example"],
    country: "Belgium",
    status: "Completed",
    progress: 100,
    recordsFound: 28,
    createdAt: "2026-10-28",
    origin: "sample",
  },
  {
    id: "proj-sample-2",
    name: "French SME consulting firms",
    sources: ["https://annuaire-conseil.example", "https://pme-france.example"],
    country: "France",
    status: "Completed",
    progress: 100,
    recordsFound: 31,
    createdAt: "2026-10-22",
    origin: "sample",
  },
  {
    id: "proj-sample-3",
    name: "Luxembourg digital agencies",
    sources: ["https://lux-digital.example"],
    country: "Luxembourg",
    status: "Running",
    progress: 64,
    recordsFound: 9,
    createdAt: "2026-11-03",
    origin: "sample",
  },
  {
    id: "proj-sample-4",
    name: "Textile & design studios",
    sources: ["https://atelier-registry.example"],
    country: "France",
    status: "Queued",
    progress: 0,
    recordsFound: 0,
    createdAt: "2026-11-04",
    origin: "sample",
  },
  {
    id: "proj-sample-5",
    name: "Energy sector contacts",
    sources: ["https://energie-annuaire.example"],
    country: "Belgium",
    status: "Failed",
    progress: 37,
    recordsFound: 4,
    createdAt: "2026-10-15",
    origin: "sample",
  },
];

/** Sample extraction activity for the last 14 days (ending 2026-11-04). */
export const SAMPLE_ACTIVITY: { date: string; extracted: number; verified: number }[] = [
  [18, 11], [24, 15], [9, 6], [31, 20], [27, 19], [14, 9], [6, 4],
  [35, 24], [42, 29], [38, 26], [21, 14], [47, 33], [52, 37], [44, 31],
].map(([extracted, verified], i) => {
  const d = new Date(Date.UTC(2026, 9, 22 + i));
  return { date: d.toISOString().slice(0, 10), extracted, verified };
});
