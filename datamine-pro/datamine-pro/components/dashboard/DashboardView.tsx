"use client";

import Link from "next/link";
import { useMemo } from "react";
import { Building2, CheckCircle2, Globe2, MailCheck, PhoneCall, Rocket } from "lucide-react";
import { useApp } from "@/context/AppContext";
import { PageHeader } from "@/components/ui/PageHeader";
import { DemoNotice } from "@/components/ui/DemoNotice";
import { StatCard } from "./StatCard";
import { ActivityChart } from "./ActivityChart";
import { RecentProjects } from "./RecentProjects";
import { RecentCompanies } from "./RecentCompanies";
import { formatNumber } from "@/lib/format";

export function DashboardView() {
  const { companies, projects } = useApp();
  const isDemoData = companies.length === 0 || companies.every((company) => company.origin === "sample");

  const stats = useMemo(() => {
    const total = companies.length;
    const complete = companies.filter((c) => c.email && c.phone && c.director && c.address).length;
    return {
      total,
      complete,
      emails: companies.filter((c) => c.emailVerified).length,
      phones: companies.filter((c) => c.phoneVerified).length,
      matched: companies.filter((c) => c.b2cWebsite).length,
    };
  }, [companies]);

  const pct = (n: number) => `${Math.round((n / Math.max(stats.total, 1)) * 100)}% of total`;

  const recentCompanies = useMemo(
    () => [...companies].sort((a, b) => b.extractedAt.localeCompare(a.extractedAt)).slice(0, 6),
    [companies]
  );

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Overview of your extraction projects and collected company data."
        actions={
          <Link href="/new-extraction" className="btn-primary">
            <Rocket className="h-4 w-4" aria-hidden /> Start New Extraction
          </Link>
        }
      />
      {isDemoData && <DemoNotice />}

      <section aria-label="Key statistics" className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Total Companies" value={formatNumber(stats.total)} hint={isDemoData ? "Sample records" : "Company records"} icon={Building2} />
        <StatCard label="Successfully Extracted" value={formatNumber(stats.complete)} hint={pct(stats.complete)} icon={CheckCircle2} />
        <StatCard label="Verified Emails" value={formatNumber(stats.emails)} hint={pct(stats.emails)} icon={MailCheck} />
        <StatCard label="Verified Phone Numbers" value={formatNumber(stats.phones)} hint={pct(stats.phones)} icon={PhoneCall} />
        <StatCard label="Websites Matched" value={formatNumber(stats.matched)} hint={`${pct(stats.matched)} · B2C match`} icon={Globe2} />
      </section>

      <section className="mt-6 grid grid-cols-1 gap-6 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <ActivityChart />
        </div>
        <div className="xl:col-span-2">
          <RecentProjects projects={projects.slice(0, 4)} />
        </div>
      </section>

      <section className="mt-6">
        <RecentCompanies companies={recentCompanies} />
      </section>
    </>
  );
}
