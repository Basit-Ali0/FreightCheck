import { Link, NavLink } from "react-router-dom";

export function AppHeader() {
  return (
    <header className="border-b border-slate-200 bg-white">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6">
        <Link to="/" className="text-lg font-semibold tracking-tight text-slate-900">
          FreightCheck
        </Link>
        <nav className="flex items-center gap-4 text-sm">
          <NavLink
            to="/sessions"
            className={({ isActive }) =>
              isActive
                ? "font-medium text-slate-900"
                : "text-slate-600 hover:text-slate-900"
            }
          >
            Sessions
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
