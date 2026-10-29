import { Link, NavLink, useNavigate } from "react-router-dom";
import { User2, LogOut } from "lucide-react";
import { useAuth } from "../lib/auth";

export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const onLogout = async () => { await logout(); navigate("/"); };
  return (
    <header className="topbar" data-testid="navbar">
      <Link to="/" className="brand" data-testid="navbar-logo">
        <img src="/logo-mark.png" alt="DestinoWay" className="brand-logo" />
        <span>Destino<span className="brand-accent">Way</span></span>
      </Link>
      <nav className="nav-links">
        <NavLink to="/" end className={({isActive}) => isActive ? "nav-link active" : "nav-link"} data-testid="nav-home">Home</NavLink>
        <NavLink to="/search" className={({isActive}) => isActive ? "nav-link active" : "nav-link"} data-testid="nav-search">Discover</NavLink>
        {user && <NavLink to="/dashboard" className={({isActive}) => isActive ? "nav-link active" : "nav-link"} data-testid="nav-dashboard">My Trips</NavLink>}
      </nav>
      <div className="top-actions">
        {user ? (
          <>
            <button className="btn-ghost" onClick={() => navigate("/dashboard")} data-testid="navbar-profile">
              <User2 size={14}/> {user.name?.split(" ")[0] || "Account"}
            </button>
            <button className="btn-ghost" onClick={onLogout} data-testid="navbar-logout" title="Log out">
              <LogOut size={14} />
            </button>
          </>
        ) : (
          <>
            <button className="btn-ghost" onClick={() => navigate("/login")} data-testid="navbar-login">Log in</button>
            <button className="btn-primary" onClick={() => navigate("/login?mode=signup")} data-testid="navbar-signup">Sign up</button>
          </>
        )}
      </div>
    </header>
  );
}
