import { Link, NavLink } from "react-router-dom";

export default function Navbar() {
    const linkClass = ({ isActive }: { isActive: boolean }) =>
        `btn btn-ghost ${isActive ? "btn-active" : ""}`;

    return (
        <div className="navbar bg-base-100 shadow-lg">
            <div className="flex-1">
                <Link to="/" className="btn btn-ghost text-xl">PopActa Draft App</Link>
            </div>
            <div className="flex-none gap-2">
                <NavLink to="/" className={linkClass}>Home</NavLink>
                <NavLink to="/players" className={linkClass}>Players</NavLink>
                <NavLink to="/settings" className={linkClass}>Settings</NavLink>
            </div>
        </div>
    );
}