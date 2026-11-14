"use client";

import { useEffect, useState } from "react";
import { apiGet } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

export default function AdminSystemPage() {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [metricsSample, setMetricsSample] = useState<string>("");

  useEffect(() => {
    apiGet<Record<string, unknown>>("/api/v1/health")
      .then(setHealth)
      .catch(console.error);
    fetch("/metrics")
      .then((r) => r.text())
      .then((txt) =>
        setMetricsSample(
          txt
            .split("\n")
            .filter((line) => line.startsWith("jobre_") || line.startsWith("# HELP jobre_"))
            .join("\n")
        )
      )
      .catch(() => setMetricsSample("Unable to fetch /metrics"));
  }, []);

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200 p-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            System Health, Storage & Telemetry
          </h1>
          <p className="text-sm text-slate-600">
            Live probes for PostgreSQL 17, Redis 8 priority queues + DLQ, search
            projection backend, raw gzip storage, and Prometheus metrics.
          </p>
        </div>
        {health && <StatusBadge status={String(health.status || "UNKNOWN")} />}
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h2 className="font-bold text-sm text-slate-900 mb-3">
          Component Health JSON (/api/v1/health)
        </h2>
        <pre className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs overflow-x-auto">
          {JSON.stringify(health, null, 2)}
        </pre>
      </div>

      <div className="bg-white rounded-2xl border border-slate-200 p-6">
        <h2 className="font-bold text-sm text-slate-900 mb-3">
          Prometheus Jobre Metrics (/metrics)
        </h2>
        <pre className="p-4 rounded-xl bg-slate-900 text-emerald-300 text-xs overflow-x-auto max-h-80">
          {metricsSample || "No jobre_* metrics emitted yet."}
        </pre>
      </div>
    </div>
  );
}
