"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Search, SlidersHorizontal, RotateCcw } from "lucide-react";
import { apiGet, SearchResponse, formatEnumLabel } from "@/lib/api";
import { JobCard } from "@/components/JobCard";

function JobsSearchInner() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [q, setQ] = useState(searchParams.get("q") || "");
  const [location, setLocation] = useState(searchParams.get("location") || "");
  const [company, setCompany] = useState(searchParams.get("company") || "");
  const [workplaceType, setWorkplaceType] = useState(
    searchParams.get("workplace_type") || ""
  );
  const [employmentType, setEmploymentType] = useState(
    searchParams.get("employment_type") || ""
  );
  const [platform, setPlatform] = useState(searchParams.get("platform") || "");
  const [postedWithinDays, setPostedWithinDays] = useState(
    searchParams.get("posted_within_days") || ""
  );
  const [salaryMin, setSalaryMin] = useState(searchParams.get("salary_min") || "");
  const [status, setStatus] = useState(searchParams.get("status") || "ACTIVE");
  const [sortBy, setSortBy] = useState(searchParams.get("sort_by") || "relevance");
  const [page, setPage] = useState(Number(searchParams.get("page") || "1"));

  const [data, setData] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const runQuery = useCallback(
    async (targetPage: number) => {
      setLoading(true);
      setError(null);
      const params = new URLSearchParams();
      if (q.trim()) params.set("q", q.trim());
      if (location.trim()) params.set("location", location.trim());
      if (company.trim()) params.set("company", company.trim());
      if (workplaceType) params.set("workplace_type", workplaceType);
      if (employmentType) params.set("employment_type", employmentType);
      if (platform) params.set("platform", platform);
      if (postedWithinDays) params.set("posted_within_days", postedWithinDays);
      if (salaryMin) params.set("salary_min", salaryMin);
      if (status) params.set("status", status);
      if (sortBy) params.set("sort_by", sortBy);
      params.set("page", String(targetPage));
      params.set("page_size", "15");

      router.replace(`/jobs?${params.toString()}`, { scroll: false });
      try {
        const res = await apiGet<SearchResponse>(
          `/api/v1/jobs/search?${params.toString()}`
        );
        setData(res);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
      } finally {
        setLoading(false);
      }
    },
    [
      q,
      location,
      company,
      workplaceType,
      employmentType,
      platform,
      postedWithinDays,
      salaryMin,
      status,
      sortBy,
      router,
    ]
  );

  useEffect(() => {
    runQuery(page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [workplaceType, employmentType, platform, postedWithinDays, status, sortBy, page]);

  const handleReset = () => {
    setQ("");
    setLocation("");
    setCompany("");
    setWorkplaceType("");
    setEmploymentType("");
    setPlatform("");
    setPostedWithinDays("");
    setSalaryMin("");
    setStatus("ACTIVE");
    setSortBy("relevance");
    setPage(1);
    router.push("/jobs");
  };

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="bg-white rounded-2xl border border-slate-200 p-4 shadow-2xs mb-6">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            setPage(1);
            runQuery(1);
          }}
          className="grid grid-cols-1 md:grid-cols-12 gap-3"
        >
          <div className="md:col-span-5 relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3.5" />
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Keywords, title, skills..."
              className="w-full pl-10 pr-3 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="md:col-span-3">
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="Location (e.g. Remote, New York, Germany)"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="md:col-span-2">
            <input
              type="text"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="Employer name"
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-blue-500"
            />
          </div>
          <div className="md:col-span-2 flex gap-2">
            <button
              type="submit"
              className="flex-1 bg-slate-900 hover:bg-blue-600 text-white font-semibold text-sm rounded-xl px-4 py-2.5 transition-colors"
            >
              Search
            </button>
            <button
              type="button"
              onClick={handleReset}
              title="Reset filters"
              className="px-3 py-2.5 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </form>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <aside className="lg:col-span-3 space-y-5">
          <div className="bg-white rounded-xl border border-slate-200 p-4 space-y-4">
            <div className="flex items-center gap-2 font-semibold text-sm text-slate-900 pb-2 border-b border-slate-100">
              <SlidersHorizontal className="w-4 h-4 text-blue-600" />
              Search Filters
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Workplace Type
              </label>
              <select
                value={workplaceType}
                onChange={(e) => {
                  setPage(1);
                  setWorkplaceType(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="">All Workplaces</option>
                <option value="REMOTE">Remote</option>
                <option value="HYBRID">Hybrid</option>
                <option value="ON_SITE">On-Site</option>
                <option value="UNKNOWN">Unspecified</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Employment Type
              </label>
              <select
                value={employmentType}
                onChange={(e) => {
                  setPage(1);
                  setEmploymentType(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="">All Employment Types</option>
                <option value="FULL_TIME">Full Time</option>
                <option value="PART_TIME">Part Time</option>
                <option value="CONTRACT">Contract</option>
                <option value="TEMPORARY">Temporary</option>
                <option value="INTERNSHIP">Internship</option>
                <option value="APPRENTICESHIP">Apprenticeship</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Source Platform
              </label>
              <select
                value={platform}
                onChange={(e) => {
                  setPage(1);
                  setPlatform(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="">All Verified Platforms</option>
                {(data?.facets?.platforms || []).map((b) => (
                  <option key={b.value} value={b.value}>
                    {b.value} ({b.count})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Date Posted / Indexed
              </label>
              <select
                value={postedWithinDays}
                onChange={(e) => {
                  setPage(1);
                  setPostedWithinDays(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="">Any time</option>
                <option value="1">Last 24 hours</option>
                <option value="7">Last 7 days</option>
                <option value="30">Last 30 days</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Minimum Salary (Annual/Raw)
              </label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={salaryMin}
                  onChange={(e) => setSalaryMin(e.target.value)}
                  placeholder="e.g. 100000"
                  className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
                />
                <button
                  type="button"
                  onClick={() => {
                    setPage(1);
                    runQuery(1);
                  }}
                  className="px-3 py-2 rounded-lg bg-slate-100 hover:bg-slate-200 text-xs font-semibold"
                >
                  Apply
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Lifecycle Status
              </label>
              <select
                value={status}
                onChange={(e) => {
                  setPage(1);
                  setStatus(e.target.value);
                }}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm"
              >
                <option value="ACTIVE">Active Only</option>
                <option value="POSSIBLY_CLOSED">Possibly Closed</option>
                <option value="CLOSED">Closed</option>
              </select>
            </div>
          </div>

          {data?.facets?.workplace_type && data.facets.workplace_type.length > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 p-4">
              <div className="text-xs font-semibold uppercase text-slate-500 mb-2">
                Workplace Breakdown
              </div>
              <div className="space-y-1.5">
                {data.facets.workplace_type.map((b) => (
                  <button
                    key={b.value}
                    onClick={() => {
                      setPage(1);
                      setWorkplaceType(workplaceType === b.value ? "" : b.value);
                    }}
                    className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg text-xs ${
                      workplaceType === b.value
                        ? "bg-blue-50 text-blue-700 font-semibold"
                        : "hover:bg-slate-50 text-slate-700"
                    }`}
                  >
                    <span>{formatEnumLabel(b.value)}</span>
                    <span className="font-mono">{b.count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </aside>

        <div className="lg:col-span-9 space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 bg-white rounded-xl border border-slate-200 px-4 py-3">
            <div className="text-sm text-slate-700">
              {loading ? (
                "Searching canonical index..."
              ) : (
                <>
                  Showing{" "}
                  <span className="font-bold text-slate-900">
                    {data?.total.toLocaleString() ?? 0}
                  </span>{" "}
                  matching jobs{" "}
                  {data && (
                    <span className="text-xs text-slate-400 ml-2">
                      ({data.backend_used} • {data.latency_ms}ms)
                    </span>
                  )}
                </>
              )}
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="text-slate-500 text-xs">Sort:</span>
              <select
                value={sortBy}
                onChange={(e) => {
                  setPage(1);
                  setSortBy(e.target.value);
                }}
                className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium"
              >
                <option value="relevance">Relevance</option>
                <option value="newest">Newest Posted</option>
                <option value="recently_seen">Recently Verified</option>
                <option value="salary_desc">Highest Compensation</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded-xl p-4 text-sm">
              {error}
            </div>
          )}

          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-36 rounded-xl bg-white border border-slate-200 animate-pulse"
                />
              ))}
            </div>
          ) : data && data.items.length === 0 ? (
            <div className="bg-white rounded-xl border border-slate-200 p-12 text-center">
              <p className="text-slate-700 font-medium">
                No normalized job listings matched your current filter combination.
              </p>
              <button
                onClick={handleReset}
                className="mt-3 px-4 py-2 rounded-lg bg-slate-900 text-white text-xs font-semibold"
              >
                Clear all filters
              </button>
            </div>
          ) : (
            <div className="space-y-3">
              {data?.items.map((job) => (
                <JobCard key={job.id} job={job} />
              ))}
            </div>
          )}

          {data && data.total_pages > 1 && (
            <div className="flex items-center justify-between pt-4">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-4 py-2 rounded-lg border border-slate-200 bg-white text-sm font-medium disabled:opacity-40"
              >
                ← Previous
              </button>
              <span className="text-sm text-slate-600">
                Page <span className="font-semibold">{data.page}</span> of{" "}
                <span className="font-semibold">{data.total_pages}</span>
              </span>
              <button
                disabled={page >= data.total_pages}
                onClick={() => setPage((p) => p + 1)}
                className="px-4 py-2 rounded-lg border border-slate-200 bg-white text-sm font-medium disabled:opacity-40"
              >
                Next →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function JobsSearchPage() {
  return (
    <Suspense
      fallback={
        <div className="max-w-7xl mx-auto px-4 py-12 text-sm text-slate-500">
          Loading search interface...
        </div>
      }
    >
      <JobsSearchInner />
    </Suspense>
  );
}
