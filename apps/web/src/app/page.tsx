"use client";

import { useEffect, useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Search,
  MapPin,
  Database,
  CheckCircle2,
  GitMerge,
  Globe,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import { apiGet, StatsResponse, SearchResponse, formatDateTime } from "@/lib/api";
import { JobCard } from "@/components/JobCard";

export default function HomePage() {
  const router = useRouter();
  const [keyword, setKeyword] = useState("");
  const [location, setLocation] = useState("");
  const [workplace, setWorkplace] = useState("");
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [recentJobs, setRecentJobs] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      apiGet<StatsResponse>("/api/v1/stats"),
      apiGet<SearchResponse>("/api/v1/jobs/search?page=1&page_size=6&sort_by=newest"),
    ])
      .then(([s, r]) => {
        setStats(s);
        setRecentJobs(r);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    const params = new URLSearchParams();
    if (keyword.trim()) params.set("q", keyword.trim());
    if (location.trim()) params.set("location", location.trim());
    if (workplace) params.set("workplace_type", workplace);
    router.push(`/jobs?${params.toString()}`);
  };

  return (
    <div>
      <section className="bg-slate-900 text-white border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16 sm:py-20">
          <div className="max-w-3xl">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-500/15 border border-blue-400/30 text-blue-300 text-xs font-medium mb-5">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Live Verified Index • Zero Synthetic Listings
            </div>
            <h1 className="text-4xl sm:text-5xl font-bold tracking-tight leading-tight">
              One index. Every opportunity.
            </h1>
            <p className="mt-4 text-lg text-slate-300 leading-relaxed">
              Jobre continuously discovers, ingests, normalizes, deduplicates, and monitors
              live vacancies directly from employer Applicant Tracking Systems and
              independent job boards across 78 tracked platforms.
            </p>
          </div>

          <form
            onSubmit={handleSearch}
            className="mt-8 bg-white rounded-2xl p-2.5 shadow-xl grid grid-cols-1 md:grid-cols-12 gap-2"
          >
            <div className="md:col-span-5 flex items-center gap-2.5 px-3 py-2 rounded-xl bg-slate-50">
              <Search className="w-5 h-5 text-slate-400 shrink-0" />
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Role, skill, or company (e.g. Engineer, Marketing, Cloudflare)"
                className="w-full bg-transparent text-slate-900 placeholder:text-slate-400 text-sm focus:outline-none"
              />
            </div>
            <div className="md:col-span-3 flex items-center gap-2.5 px-3 py-2 rounded-xl bg-slate-50">
              <MapPin className="w-5 h-5 text-slate-400 shrink-0" />
              <input
                type="text"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="City, state, or country"
                className="w-full bg-transparent text-slate-900 placeholder:text-slate-400 text-sm focus:outline-none"
              />
            </div>
            <div className="md:col-span-2 flex items-center px-3 py-2 rounded-xl bg-slate-50">
              <select
                value={workplace}
                onChange={(e) => setWorkplace(e.target.value)}
                className="w-full bg-transparent text-slate-800 text-sm focus:outline-none"
              >
                <option value="">Any Workplace</option>
                <option value="REMOTE">Remote</option>
                <option value="HYBRID">Hybrid</option>
                <option value="ON_SITE">On-site</option>
              </select>
            </div>
            <div className="md:col-span-2">
              <button
                type="submit"
                className="w-full h-full min-h-[44px] bg-blue-600 hover:bg-blue-700 text-white font-semibold text-sm rounded-xl transition-colors flex items-center justify-center gap-1.5"
              >
                Search Jobs <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </form>

          {stats && (
            <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="bg-slate-800/70 border border-slate-700/80 rounded-xl p-4">
                <div className="text-xs text-slate-400 uppercase tracking-wider">
                  Active Jobs Indexed
                </div>
                <div className="mt-1 text-2xl font-bold text-white">
                  {stats.active_jobs.toLocaleString()}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  Across {stats.total_companies} employers
                </div>
              </div>
              <div className="bg-slate-800/70 border border-slate-700/80 rounded-xl p-4">
                <div className="text-xs text-slate-400 uppercase tracking-wider">
                  Verified Platforms
                </div>
                <div className="mt-1 text-2xl font-bold text-emerald-400">
                  {stats.verified_platforms}{" "}
                  <span className="text-sm font-normal text-slate-400">
                    / {stats.total_required_platforms} cataloged
                  </span>
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  17 ATS + 5 Job-Board engines live
                </div>
              </div>
              <div className="bg-slate-800/70 border border-slate-700/80 rounded-xl p-4">
                <div className="text-xs text-slate-400 uppercase tracking-wider">
                  Monitored Sources
                </div>
                <div className="mt-1 text-2xl font-bold text-white">
                  {stats.active_sources}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  {stats.successful_ingestion_runs} verified runs
                </div>
              </div>
              <div className="bg-slate-800/70 border border-slate-700/80 rounded-xl p-4">
                <div className="text-xs text-slate-400 uppercase tracking-wider">
                  Cross-Source Merges
                </div>
                <div className="mt-1 text-2xl font-bold text-indigo-300">
                  {stats.duplicate_groups}
                </div>
                <div className="text-xs text-slate-400 mt-1">
                  Last sync {formatDateTime(stats.last_successful_refresh)}
                </div>
              </div>
            </div>
          )}
        </div>
      </section>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 space-y-12">
        {stats && stats.jobs_by_platform.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                  <Globe className="w-5 h-5 text-blue-600" />
                  Live Verified Platform Sources
                </h2>
                <p className="text-sm text-slate-600">
                  Click any verified ATS or job-board connector to filter real normalized listings.
                </p>
              </div>
              <Link
                href="/about"
                className="text-sm font-semibold text-blue-600 hover:text-blue-800"
              >
                Full 78-platform matrix →
              </Link>
            </div>
            <div className="flex flex-wrap gap-2">
              {stats.jobs_by_platform.map((p) => (
                <Link
                  key={p.connector_key}
                  href={`/jobs?platform=${encodeURIComponent(p.connector_key)}`}
                  className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl bg-white border border-slate-200 hover:border-blue-500 text-sm font-medium text-slate-800 shadow-2xs transition-colors"
                >
                  <span>{p.platform}</span>
                  <span className="text-[11px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                    {p.jobs_count}
                  </span>
                </Link>
              ))}
            </div>
          </section>
        )}

        <section>
          <div className="flex items-center justify-between mb-5">
            <div>
              <h2 className="text-xl font-bold text-slate-900 flex items-center gap-2">
                <Database className="w-5 h-5 text-blue-600" />
                Latest Normalized Opportunities
              </h2>
              <p className="text-sm text-slate-600">
                Canonical records with preserved raw snapshots, source provenance, and lifecycle status.
              </p>
            </div>
            <Link
              href="/jobs"
              className="text-sm font-semibold text-blue-600 hover:text-blue-800"
            >
              Browse all {stats?.active_jobs ?? ""} jobs →
            </Link>
          </div>

          {loading ? (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {[1, 2, 3, 4].map((n) => (
                <div
                  key={n}
                  className="h-40 rounded-xl bg-white border border-slate-200 animate-pulse"
                />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {recentJobs?.items.map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
          )}
        </section>

        <section className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <GitMerge className="w-6 h-6 text-indigo-600 mb-3" />
            <h3 className="font-semibold text-slate-900">
              Multi-Signal Deduplication
            </h3>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">
              Matches identical openings across company ATS boards and third-party
              job boards using canonical application URLs, ATS requisition tokens,
              employer identity, location compatibility, and description similarity—never
              title alone.
            </p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <ShieldCheck className="w-6 h-6 text-emerald-600 mb-3" />
            <h3 className="font-semibold text-slate-900">
              Safe Multi-Run Closure Policy
            </h3>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">
              Transient HTTP errors, timeouts, rate limits, or maintenance windows
              never close active jobs. Jobs transition through{" "}
              <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">
                POSSIBLY_CLOSED
              </code>{" "}
              to <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">CLOSED</code>{" "}
              only after consecutive verified complete snapshots.
            </p>
          </div>
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <CheckCircle2 className="w-6 h-6 text-blue-600 mb-3" />
            <h3 className="font-semibold text-slate-900">
              Evidence-Backed Coverage
            </h3>
            <p className="mt-2 text-sm text-slate-600 leading-relaxed">
              Every single platform in our 78-platform catalog carries an honest,
              verifiable implementation state backed by retained gzip raw snapshots
              and cryptographic run IDs.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
