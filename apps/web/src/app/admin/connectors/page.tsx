"use client";

import { useEffect, useState, FormEvent } from "react";
import { Play } from "lucide-react";
import { adminFetch, PlatformCoverageEntry } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function AdminConnectorsPage() {
  const [connectors, setConnectors] = useState<PlatformCoverageEntry[]>([]);
  const [selectedKey, setSelectedKey] = useState("greenhouse");
  const [testUrl, setTestUrl] = useState("https://boards.greenhouse.io/cloudflare");
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(
    null
  );
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    adminFetch<{ items: PlatformCoverageEntry[] }>("/api/v1/admin/connectors")
      .then((res) => setConnectors(res.items))
      .catch(console.error);
  }, []);

  const implemented = connectors.filter((c) => c.connector_registered_in_code);

  const handleLiveTest = async (e: FormEvent) => {
    e.preventDefault();
    setTesting(true);
    setTestResult(null);
    try {
      const res = await adminFetch<Record<string, unknown>>(
        `/api/v1/admin/connectors/${selectedKey}/test`,
        {
          method: "POST",
          body: JSON.stringify({ source_url: testUrl.trim(), max_jobs: 3 }),
        }
      );
      setTestResult(res);
    } catch (err) {
      setTestResult({
        error: err instanceof Error ? err.message : "Test failed",
      });
    } finally {
      setTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Connector Health & Live Probe
        </h1>
        <p className="text-sm text-slate-600">
          Monitor response latency, error counters, rate limits, and execute
          on-demand live probes against any implemented connector.
        </p>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3">
        <h2 className="font-bold text-sm text-slate-900">
          Interactive Live Connector Probe
        </h2>
        <form
          onSubmit={handleLiveTest}
          className="grid grid-cols-1 sm:grid-cols-12 gap-2"
        >
          <select
            value={selectedKey}
            onChange={(e) => {
              const key = e.target.value;
              setSelectedKey(key);
              const found = implemented.find((x) => x.connector_key === key);
              if (found?.verification_evidence?.example_source_url) {
                setTestUrl(found.verification_evidence.example_source_url);
              }
            }}
            className="sm:col-span-3 px-3 py-2 rounded-xl border border-slate-200 text-xs font-mono"
          >
            {implemented.map((c) => (
              <option key={c.connector_key} value={c.connector_key}>
                {c.connector_key}
              </option>
            ))}
          </select>
          <input
            type="url"
            required
            value={testUrl}
            onChange={(e) => setTestUrl(e.target.value)}
            className="sm:col-span-7 px-3 py-2 rounded-xl border border-slate-200 text-xs"
          />
          <button
            disabled={testing}
            type="submit"
            className="sm:col-span-2 inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 text-white text-xs font-semibold disabled:opacity-50"
          >
            <Play className="w-3.5 h-3.5" />
            {testing ? "Probing..." : "Probe"}
          </button>
        </form>

        {testResult && (
          <pre className="p-3.5 rounded-xl bg-slate-900 text-emerald-300 text-[11px] overflow-x-auto max-h-72">
            {JSON.stringify(testResult, null, 2)}
          </pre>
        )}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-5">
        <h2 className="font-bold text-sm text-slate-900 mb-3">
          Implemented Connectors ({implemented.length})
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-200 uppercase text-slate-500">
                <th className="py-2.5 pr-3">Connector</th>
                <th className="py-2.5 pr-3">Status</th>
                <th className="py-2.5 pr-3">Health</th>
                <th className="py-2.5 pr-3">Rate Limit</th>
                <th className="py-2.5 pr-3">Failed Reqs</th>
                <th className="py-2.5">Avg Latency</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {implemented.map((c) => (
                <tr key={c.connector_key}>
                  <td className="py-2.5 pr-3 font-semibold text-slate-900">
                    {c.name}{" "}
                    <span className="font-mono text-slate-400">
                      ({c.connector_key})
                    </span>
                  </td>
                  <td className="py-2.5 pr-3">
                    <StatusBadge status={c.implementation_status} />
                  </td>
                  <td className="py-2.5 pr-3">
                    <StatusBadge status={c.health_status} />
                  </td>
                  <td className="py-2.5 pr-3 font-mono">
                    {c.rate_limit_rpm} rpm
                  </td>
                  <td className="py-2.5 pr-3 font-mono">{c.failed_requests}</td>
                  <td className="py-2.5 font-mono">
                    {c.average_response_time_ms
                      ? `${Math.round(c.average_response_time_ms)}ms`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
