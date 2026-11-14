"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Layers, Search, Building2, ShieldCheck, Info } from "lucide-react";

export function Navbar() {
  const pathname = usePathname() || "/";

  const links = [
    { href: "/jobs", label: "Search Jobs", icon: Search },
    { href: "/companies", label: "Companies", icon: Building2 },
    { href: "/about", label: "Coverage & Methodology", icon: Info },
    { href: "/admin", label: "Admin Console", icon: ShieldCheck },
  ];

  return (
    <header className="sticky top-0 z-40 bg-white/95 backdrop-blur border-b border-slate-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-9 h-9 rounded-lg bg-slate-900 text-white flex items-center justify-center shadow-sm group-hover:bg-blue-600 transition-colors">
            <Layers className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-lg tracking-tight text-slate-900">
              Jobre
            </span>
            <span className="hidden sm:inline-block ml-2 text-xs font-medium text-slate-500 border-l border-slate-300 pl-2">
              One index. Every opportunity.
            </span>
          </div>
        </Link>

        <nav className="flex items-center gap-1 sm:gap-2">
          {links.map((item) => {
            const Icon = item.icon;
            const active =
              pathname === item.href ||
              (item.href !== "/" && pathname.startsWith(item.href));
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? "bg-slate-900 text-white"
                    : "text-slate-600 hover:text-slate-900 hover:bg-slate-100"
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="hidden md:inline">{item.label}</span>
                <span className="md:hidden">
                  {item.label.split(" ")[0]}
                </span>
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
