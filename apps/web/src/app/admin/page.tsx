"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { RefreshCw, Database, CheckCircle2, GitMerge, Play } from "lucide-react";
import { apiGet, adminFetch, StatsResponse, formatDateTime } from "@/lib/api";

export default function AdminOverviewPage() {
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    Promise.all([
      apiGet<StatsResponse>("/api/v1/stats"),
      apiGet<Record<string, unknown>>("/api/v1/health"),
    ])
      .then(([s, h]) => {
        setStats(s);
        setHealth(h);
      })
      .catch(console.error);
  };

  useEffect(() => {
    load();
  }, []);

  const triggerSchedulerTick = async () => {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        "/api/v1/admin/scheduler/tick",
        { method: "POST" }
      );
      setActionMsg(`Scheduler tick completed: ${JSON.stringify(res)}`);
      load();
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const triggerSearchRebuild = async () => {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        "/api/v1/admin/search/rebuild",
        { method: "POST" }
      );
      setActionMsg(`Search index rebuilt from PostgreSQL: ${JSON.stringify(res)}`);
    } catch (err) {
      setActionMsg(err instanceof Error ? err.message : "Failed");
    } finally {
      setBusy(false);
    }
  };

  const components = (health?.components || {}) as Record<
    string,
    Record<string, unknown>
  >;
  const queues = (components?.redis?.queues || {}) as Record<string, number>;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Operational Overview
          </h1>
          <p className="text-sm text-slate-600">
            Real-time metrics computed directly from PostgreSQL 17 and Redis 8.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            disabled={busy}
            onClick={triggerSchedulerTick}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-blue-600 text-white text-xs font-semibold disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            Dispatch Due Sources
          </button>
          <button
            disabled={busy}
            onClick={triggerSearchRebuild}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold disabled:opacity-50"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            Rebuild Search Projection
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="bg-blue-50 border border-blue-200 text-blue-900 rounded-xl p-3.5 text-xs font-mono">
          {actionMsg}
        </div>
      )}

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="text-xs text-slate-500 uppercase font-semibold">
              Active / Total Jobs
            </div>
            <div className="mt-1 text-2xl font-bold text-slate-900">
              {stats.active_jobs} / {stats.indexed_jobs}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Possibly closed: {stats.possibly_closed_jobs} • Closed:{" "}
              {stats.closed_jobs}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="text-xs text-slate-500 uppercase font-semibold">
              Verified Platforms
            </div>
            <div className="mt-1 text-2xl font-bold text-emerald-600">
              {stats.verified_platforms} / {stats.total_required_platforms}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {stats.active_sources} active sources
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="text-xs text-slate-500 uppercase font-semibold">
              Ingestion Runs
            </div>
            <div className="mt-1 text-2xl font-bold text-slate-900">
              {stats.successful_ingestion_runs} / {stats.total_ingestion_runs}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Failed runs: {stats.failed_ingestion_runs}
            </div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4">
            <div className="text-xs text-slate-500 uppercase font-semibold">
              Duplicate Groups
            </div>
            <div className="mt-1 text-2xl font-bold text-indigo-600">
              {stats.duplicate_groups}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              Pending review: {stats.pending_duplicate_reviews}
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-bold text-slate-900 flex items-center gap-2">
              <Database className="w-4 h-4 text-blue-600" />
              Jobs Indexed by Verified Platform
            </h2>
            <Link
              href="/admin/coverage"
              className="text-xs font-semibold text-blue-600 hover:underline"
            >
              View 78-platform matrix →
            </Link>
          </div>
          <div className="space-y-2.5 max-h-80 overflow-y-auto pr-1">
            {stats?.jobs_by_platform.map((item) => {
              const max = Math.max(
                1,
                ...(stats.jobs_by_platform.map((x) => x.jobs_count) || [1])
              );
              const pct = Math.round((item.jobs_count / max) * 100);
              return (
                <div key={item.connector_key} className="text-xs">
                  <div className="flex justify-between mb-1">
                    <span className="font-medium text-slate-800">
                      {item.platform}{" "}
                      <span className="text-slate-400">({item.category})</span>
                    </span>
                    <span className="font-mono font-semibold">
                      {item.jobs_count}
                    </span>
                  </div>
                  <div className="h-2 rounded-full bg-slate-100 overflow-hidden">
                    <div
                      className="h-full bg-blue-600 rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <div className="space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200 p-6">
            <h2 className="font-bold text-slate-900 mb-3 flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              Redis Worker Priority Queues
            </h2>
            <div className="grid grid-cols-4 gap-2 text-center">
              {(["high", "normal", "low", "dlq"] as const).map((qName) => (
                <div
                  key={qName}
                  className="p-3 rounded-xl bg-slate-50 border border-slate-200"
                >
                  <div className="text-[11px] uppercase font-semibold text-slate-500">
                    {qName}
                  </div>
                  <div className="mt-1 text-lg font-bold font-mono text-slate-900">
                    {queues[qName] ?? 0}
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 text-xs text-slate-500">
              Last successful refresh:{" "}
              <span className="font-medium text-slate-800">
                {formatDateTime(stats?.last_successful_refresh)}
              </span>
            </div>
          </div>

          <div className="bg-white rounded-2xl border border-slate-200 p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-bold text-slate-900 flex items-center gap-2">
                <GitMerge className="w-4 h-4 text-indigo-600" />
                Workplace Distribution
              </h2>
              <Link
                href="/admin/duplicates"
                className="text-xs font-semibold text-indigo-600 hover:underline"
              >
                Inspect Duplicate Groups →
              </Link>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              {stats?.jobs_by_workplace.map((w) => (
                <div
                  key={w.workplace_type}
                  className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs"
                >
                  <span className="font-medium text-slate-700">
                    {w.workplace_type}
                  </span>
                  <span className="font-mono font-bold text-slate-900">
                    {w.count}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
