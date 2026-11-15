import { Navigate, NavLink, Outlet, useNavigate } from "react-router-dom";
import { getToken, setToken } from "../lib/client";
import { StatusBanner } from "./StatusBanner";

const LINKS = [
  ["/jobs", "Inbox"], ["/approvals", "Approvals"], ["/pipeline", "Pipeline"], ["/messages", "Messages"],
  ["/analytics", "Analytics"], ["/settings", "Settings"],
];

export function Layout() {
  const navigate = useNavigate();
  if (!getToken()) return <Navigate to="/login" replace />;
  return (
    <div className="min-h-screen">
      <StatusBanner />
      <header className="border-b border-slate-200 bg-white">
        <nav aria-label="Main" className="mx-auto flex max-w-6xl flex-wrap items-center gap-1 px-4 py-2">
          <span className="mr-3 font-bold text-indigo-700">GigBid</span>
          {LINKS.map(([to, label]) => (
            <NavLink key={to} to={to}
              className={({ isActive }) => `rounded px-2 py-1 text-sm ${isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100"}`}>
              {label}
            </NavLink>
          ))}
          <button type="button" className="ml-auto rounded px-2 py-1 text-sm text-slate-600 hover:bg-slate-100"
            onClick={() => { setToken(null); navigate("/login"); }}>
            Sign out
          </button>
        </nav>
      </header>
      <main><Outlet /></main>
    </div>
  );
}
