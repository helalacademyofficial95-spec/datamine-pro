import type { Company } from "./types";
import { buildCsv, EXPORT_COLUMNS } from "./csv";

/** e.g. datamine-pro-companies-2026-11-05-0942.csv */
export function buildFilename(ext: "csv" | "xlsx"): string {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  const stamp = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
  return `datamine-pro-companies-${stamp}.${ext}`;
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadCsv(companies: Company[], filename: string) {
  // The BOM (﻿) makes Excel read accents (é, è, ü) correctly.
  const blob = new Blob(["﻿", buildCsv(companies)], { type: "text/csv;charset=utf-8" });
  triggerDownload(blob, filename);
}

export async function downloadXlsx(companies: Company[], filename: string) {
  // Loaded on demand so the Excel library is only downloaded when someone exports.
  const mod = (await import("exceljs")) as unknown as {
    Workbook?: typeof import("exceljs").Workbook;
    default?: { Workbook: typeof import("exceljs").Workbook };
  };
  const Workbook = mod.Workbook ?? mod.default?.Workbook;
  if (!Workbook) throw new Error("Excel library failed to load");

  const workbook = new Workbook();
  workbook.creator = "DataMine Pro";
  workbook.created = new Date();
  const sheet = workbook.addWorksheet("Companies", { views: [{ state: "frozen", ySplit: 1 }] });

  sheet.columns = EXPORT_COLUMNS.map((c) => ({ header: c.header, key: c.header, width: c.width }));
  for (const company of companies) {
    sheet.addRow(EXPORT_COLUMNS.map((c) => c.value(company)));
  }

  const header = sheet.getRow(1);
  header.font = { bold: true, color: { argb: "FFFFFFFF" } };
  header.fill = { type: "pattern", pattern: "solid", fgColor: { argb: "FF1E3A8A" } };
  header.alignment = { vertical: "middle" };
  header.height = 22;
  sheet.autoFilter = { from: { row: 1, column: 1 }, to: { row: 1, column: EXPORT_COLUMNS.length } };

  const turnoverCol = EXPORT_COLUMNS.findIndex((c) => c.header.startsWith("Annual Turnover")) + 1;
  sheet.getColumn(turnoverCol).numFmt = '#,##0 "€"';

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([buffer as unknown as BlobPart], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  triggerDownload(blob, filename);
}
