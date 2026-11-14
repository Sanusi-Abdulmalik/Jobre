"use client";

import { useEffect, useState, FormEvent } from "react";
import { Search, PlusCircle, RefreshCw, Upload } from "lucide-react";
import { apiGet, adminFetch, SourceItem, formatDateTime } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function AdminSourcesPage() {
  const [sources, setSources] = useState<SourceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);

  const [discoverUrl, setDiscoverUrl] = useState("");
  const [discoverRes, setDiscoverRes] = useState<Record<string, unknown> | null>(
    null
  );
  const [newUrl, setNewUrl] = useState("");
  const [newCompany, setNewCompany] = useState("");
  const [runImmediately, setRunImmediately] = useState(true);

  const [bulkUrls, setBulkUrls] = useState("");
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const loadSources = () => {
    setLoading(true);
    apiGet<{ items: SourceItem[]; total: number }>(
      "/api/v1/sources?page=1&page_size=100"
    )
      .then((res) => {
        setSources(res.items);
        setTotal(res.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadSources();
  }, []);

  const handleDiscover = async (e: FormEvent) => {
    e.preventDefault();
    setDiscoverRes(null);
    setStatusMsg(null);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        "/api/v1/admin/sources/discover",
        {
          method: "POST",
          body: JSON.stringify({ url: discoverUrl.trim() }),
        }
      );
      setDiscoverRes(res);
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Discovery error");
    }
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    setStatusMsg("Registering source...");
    try {
      const res = await adminFetch<Record<string, unknown>>(
        "/api/v1/admin/sources",
        {
          method: "POST",
          body: JSON.stringify({
            source_url: newUrl.trim(),
            company_name: newCompany.trim() || undefined,
            run_immediately: runImmediately,
            max_jobs: 20,
          }),
        }
      );
      setStatusMsg(`Registered source: ${JSON.stringify(res.source || res)}`);
      setNewUrl("");
      setNewCompany("");
      loadSources();
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Registration failed");
    }
  };

  const handleBulkImport = async (e: FormEvent) => {
    e.preventDefault();
    const lines = bulkUrls
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!lines.length) return;
    setStatusMsg(`Importing ${lines.length} URL(s)...`);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        "/api/v1/admin/sources/bulk",
        {
          method: "POST",
          body: JSON.stringify({ urls: lines }),
        }
      );
      setStatusMsg(`Bulk import result: ${JSON.stringify(res)}`);
      setBulkUrls("");
      loadSources();
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Bulk import failed");
    }
  };

  const triggerRefresh = async (sourceId: string) => {
    setBusyId(sourceId);
    setStatusMsg(null);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        `/api/v1/admin/sources/${sourceId}/refresh`,
        {
          method: "POST",
          body: JSON.stringify({ async_queue: false, max_jobs: 20 }),
        }
      );
      setStatusMsg(`Refresh completed: ${JSON.stringify(res)}`);
      loadSources();
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Refresh failed");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Source Discovery & Management ({total})
        </h1>
        <p className="text-sm text-slate-600">
          Inspect URLs for ATS/job-board signatures (with SSRF protection), register
          sources idempotently, or trigger manual ingestion runs.
        </p>
      </div>

      {statusMsg && (
        <div className="bg-slate-900 text-slate-100 rounded-xl p-3.5 text-xs font-mono overflow-x-auto">
          {statusMsg}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <h2 className="font-bold text-slate-900 text-sm flex items-center gap-2">
            <Search className="w-4 h-4 text-blue-600" />
            1. Detect Platform from URL
          </h2>
          <form onSubmit={handleDiscover} className="flex gap-2">
            <input
              type="url"
              required
              value={discoverUrl}
              onChange={(e) => setDiscoverUrl(e.target.value)}
              placeholder="https://boards.greenhouse.io/cloudflare"
              className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs"
            />
            <button
              type="submit"
              className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold"
            >
              Detect
            </button>
          </form>
          {discoverRes && (
            <pre className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-[11px] overflow-x-auto">
              {JSON.stringify(discoverRes, null, 2)}
            </pre>
          )}
        </div>

        <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
          <h2 className="font-bold text-slate-900 text-sm flex items-center gap-2">
            <PlusCircle className="w-4 h-4 text-emerald-600" />
            2. Register Source & Ingest
          </h2>
          <form onSubmit={handleRegister} className="space-y-2.5">
            <input
              type="url"
              required
              value={newUrl}
              onChange={(e) => setNewUrl(e.target.value)}
              placeholder="Career page or ATS board URL"
              className="w-full px-3 py-2 rounded-xl border border-slate-200 text-xs"
            />
            <div className="flex gap-2">
              <input
                type="text"
                value={newCompany}
                onChange={(e) => setNewCompany(e.target.value)}
                placeholder="Company Name (optional)"
                className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs"
              />
              <label className="inline-flex items-center gap-1.5 text-xs text-slate-700 px-2">
                <input
                  type="checkbox"
                  checked={runImmediately}
                  onChange={(e) => setRunImmediately(e.target.checked)}
                />
                Run now
              </label>
              <button
                type="submit"
                className="px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold"
              >
                Add
              </button>
            </div>
          </form>
        </div>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
        <h2 className="font-bold text-slate-900 text-sm flex items-center gap-2">
          <Upload className="w-4 h-4 text-indigo-600" />
          Bulk URL Seed Import (One URL per line)
        </h2>
        <form onSubmit={handleBulkImport} className="flex flex-col sm:flex-row gap-2">
          <textarea
            rows={2}
            value={bulkUrls}
            onChange={(e) => setBulkUrls(e.target.value)}
            placeholder="https://jobs.ashbyhq.com/linear&#10;https://boards.greenhouse.io/cloudflare"
            className="flex-1 px-3 py-2 rounded-xl border border-slate-200 text-xs font-mono"
          />
          <button
            type="submit"
            className="px-4 py-2 rounded-xl bg-slate-900 text-white text-xs font-semibold shrink-0"
          >
            Bulk Import
          </button>
        </form>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <h2 className="font-bold text-slate-900 mb-3 text-sm">
          Registered Sources ({sources.length})
        </h2>
        {loading ? (
          <div className="text-xs text-slate-500 py-6">Loading sources...</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-slate-200 uppercase text-slate-500">
                  <th className="py-2.5 pr-3">Source</th>
                  <th className="py-2.5 pr-3">Platform</th>
                  <th className="py-2.5 pr-3">Status</th>
                  <th className="py-2.5 pr-3">Active Jobs</th>
                  <th className="py-2.5 pr-3">Last Synced</th>
                  <th className="py-2.5">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {sources.map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="py-2.5 pr-3">
                      <div className="font-semibold text-slate-900">
                        {s.source_name}
                      </div>
                      <a
                        href={s.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-blue-600 hover:underline truncate block max-w-xs"
                      >
                        {s.source_url}
                      </a>
                    </td>
                    <td className="py-2.5 pr-3 font-mono">
                      {s.platform_name || s.platform_key || "—"}
                    </td>
                    <td className="py-2.5 pr-3">
                      <StatusBadge status={s.status} />
                    </td>
                    <td className="py-2.5 pr-3 font-mono font-semibold">
                      {s.active_jobs_count}
                    </td>
                    <td className="py-2.5 pr-3 text-slate-500">
                      {formatDateTime(s.last_successful_sync_at)}
                    </td>
                    <td className="py-2.5">
                      <button
                        disabled={busyId === s.id}
                        onClick={() => triggerRefresh(s.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-slate-100 hover:bg-blue-600 hover:text-white text-slate-800 font-semibold transition-colors disabled:opacity-50"
                      >
                        <RefreshCw
                          className={`w-3 h-3 ${
                            busyId === s.id ? "animate-spin" : ""
                          }`}
                        />
                        Refresh
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
