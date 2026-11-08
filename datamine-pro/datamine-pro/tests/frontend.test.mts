// Runs with: node --experimental-strip-types --test tests/frontend.test.mts  (no extra packages)
import assert from "node:assert/strict";
import { test } from "node:test";
import { buildCsv, EXPORT_COLUMNS } from "../lib/csv.ts";
import { DEFAULT_FILTERS, categoryOptions, countActiveFilters, filterCompanies } from "../lib/filters.ts";

const base = {
  id: "1", name: "MAISON LILAS", siren: "123456789", director: "Anne Martin", email: "", phone: "",
  employees: 0, turnover: 0, country: "France", address: "5 place du Marche 69001 LYON", website: "",
  b2cWebsite: null, emailVerified: false, phoneVerified: false, verification: "Unverified",
  origin: "extracted", extractedAt: "2026-11-06",
} as any;
const rich = {
  ...base, id: "2", name: "ATELIER ROSE", country: "Belgium", website: "https://rose.example", b2cWebsite: "https://shop.rose.example",
  email: "contact@rose.example", phone: "+32 2 123 45 67", nafLabel: "Commerce de détail", verification: "Verified",
  websiteStatus: "Verified", websiteSourceUrl: "https://rose.example/mentions", b2cSourceUrl: "https://shop.rose.example",
  emailSource: "https://rose.example/contact", phoneSource: "https://rose.example/contact", checkedAt: "2026-11-06",
  employeeBand: "12", turnoverYear: 2024, turnover: 1200000, registryUrl: "https://registry.example/2",
} as any;
const rows = [base, rich];

test("export has all 24 required columns incl. Business Category, in order", () => {
  const h = EXPORT_COLUMNS.map((c) => c.header);
  assert.equal(h.length, 24);
  for (const need of ["Company Name", "Email Source URL", "Phone Source URL", "Official Website Source URL", "B2C Source URL",
    "Website Check Date", "Turnover Year", "Registry Source URL", "Data Origin", "Business Category"]) assert.ok(h.includes(need), need);
  assert.equal(h[h.length - 1], "Business Category");
});

test("CSV rows carry source URLs, category and explicit Not Found", () => {
  const lines = buildCsv(rows).split("\r\n");
  assert.equal(lines.length, 3);
  assert.match(lines[1], /Not Found/);
  assert.match(lines[2], /Commerce de détail/);
  assert.match(lines[2], /https:\/\/shop\.rose\.example/);
});

test("filters: country, website, b2c, email, phone, category, verification", () => {
  const f = (patch: object) => filterCompanies(rows, { ...DEFAULT_FILTERS, ...patch }).map((c: any) => c.id);
  assert.deepEqual(f({ country: "Belgium" }), ["2"]);
  assert.deepEqual(f({ hasWebsite: "yes" }), ["2"]);
  assert.deepEqual(f({ hasWebsite: "no" }), ["1"]);
  assert.deepEqual(f({ b2c: "yes" }), ["2"]);
  assert.deepEqual(f({ hasEmail: "yes" }), ["2"]);
  assert.deepEqual(f({ hasEmail: "no" }), ["1"]);
  assert.deepEqual(f({ hasPhone: "yes" }), ["2"]);
  assert.deepEqual(f({ category: "Commerce de détail" }), ["2"]);
  assert.deepEqual(f({ verification: "Verified" }), ["2"]);
});

test("old saved presets without the new keys still work", () => {
  const legacy: any = { search: "", country: "all", employees: "all", employeesMin: "", employeesMax: "", turnover: "all",
    turnoverMin: "", turnoverMax: "", verification: "all", b2c: "all" };
  assert.equal(filterCompanies(rows, legacy).length, 2);
  assert.equal(countActiveFilters(legacy), 0);
  assert.deepEqual(categoryOptions(rows), ["Commerce de détail"]);
});
