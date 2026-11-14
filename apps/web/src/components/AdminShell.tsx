"use client";

import { useEffect, useState, FormEvent } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Globe,
  Grid,
  PlugZap,
  PlayCircle,
  Briefcase,
  GitMerge,
  History,
  Activity,
  Lock,
  LogOut,
} from "lucide-react";
import {
  adminFetch,
  getStoredAdminKey,
  setStoredAdminKey,
  clearStoredAdminKey,
} from "@/lib/api";

const NAV_ITEMS = [
  { href: "/admin", label: "Overview", icon: LayoutDashboard },
  { href: "/admin/sources", label: "Sources & Discovery", icon: Globe },
  { href: "/admin/platform-coverage", label: "Platform Coverage (78)", icon: Grid },
  { href: "/admin/connectors", label: "Connector Health", icon: PlugZap },
  { href: "/admin/runs", label: "Ingestion Runs", icon: PlayCircle },
  { href: "/admin/jobs", label: "Job Records", icon: Briefcase },
  { href: "/admin/duplicates", label: "Duplicate Review", icon: GitMerge },
  { href: "/admin/changes", label: "Change History", icon: History },
  { href: "/admin/system", label: "System & Queues", icon: Activity },
];

export function AdminShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || "/admin";
  const [verified, setVerified] = useState(false);
  const [checking, setChecking] = useState(true);
  const [inputKey, setInputKey] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);

  useEffect(() => {
    const existing = getStoredAdminKey();
    if (!existing) {
      setChecking(false);
      return;
    }
    adminFetch<{ authenticated: boolean }>("/api/v1/admin/auth/verify", {}, existing)
      .then(() => setVerified(true))
      .catch(() => {
        clearStoredAdminKey();
        setVerified(false);
      })
      .finally(() => setChecking(false));
  }, []);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setAuthError(null);
    try {
      await adminFetch(
        "/api/v1/admin/auth/verify",
        {},
        inputKey.trim()
      );
      setStoredAdminKey(inputKey.trim());
      setVerified(true);
    } catch (err) {
      setAuthError(
        err instanceof Error ? err.message : "Invalid administrative key"
      );
    }
  };

  if (checking) {
    return (
      <div className="max-w-md mx-auto px-4 py-20 text-center text-sm text-slate-500">
        Verifying administrative credentials...
      </div>
    );
  }

  if (!verified) {
    return (
      <div className="max-w-md mx-auto px-4 py-16">
        <div className="bg-white rounded-2xl border border-slate-200 p-8 shadow-xs">
          <div className="w-11 h-11 rounded-xl bg-slate-900 text-white flex items-center justify-center mb-4">
            <Lock className="w-5 h-5" />
          </div>
          <h1 className="text-xl font-bold text-slate-900">
            Jobre Administrative Console
          </h1>
          <p className="mt-1.5 text-sm text-slate-600">
            All <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">/api/v1/admin/*</code>{" "}
            endpoints require a valid <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">X-Admin-Key</code>{" "}
            or Bearer token configured in <code className="text-xs bg-slate-100 px-1 py-0.5 rounded">JOBRE_ADMIN_API_KEY</code>.
          </p>

          <form onSubmit={handleLogin} className="mt-6 space-y-4">
            <div>
              <label className="block text-xs font-semibold uppercase text-slate-500 mb-1.5">
                Admin API Key
              </label>
              <input
                type="password"
                required
                value={inputKey}
                onChange={(e) => setInputKey(e.target.value)}
                placeholder="Enter JOBRE_ADMIN_API_KEY"
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-sm focus:outline-none focus:border-blue-500"
              />
            </div>
            {authError && (
              <div className="text-xs text-rose-600 bg-rose-50 border border-rose-200 rounded-lg p-2.5">
                {authError}
              </div>
            )}
            <button
              type="submit"
              className="w-full py-2.5 rounded-xl bg-slate-900 hover:bg-blue-600 text-white text-sm font-semibold transition-colors"
            >
              Authenticate Operator Session
            </button>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <aside className="lg:col-span-3">
          <div className="bg-white rounded-2xl border border-slate-200 p-3 sticky top-20 space-y-1">
            <div className="px-3 py-2 text-xs font-bold uppercase tracking-wider text-slate-400">
              Operator Console
            </div>
            {NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = pathname === item.href;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-colors ${
                    active
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                  }`}
                >
                  <Icon className="w-4 h-4 shrink-0" />
                  <span>{item.label}</span>
                </Link>
              );
            })}
            <div className="pt-2 mt-2 border-t border-slate-100">
              <button
                onClick={() => {
                  clearStoredAdminKey();
                  setVerified(false);
                  setInputKey("");
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium text-rose-600 hover:bg-rose-50"
              >
                <LogOut className="w-4 h-4" />
                Sign Out
              </button>
            </div>
          </div>
        </aside>

        <div className="lg:col-span-9 min-w-0">{children}</div>
      </div>
    </div>
  );
}
