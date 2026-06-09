import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./auth";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Units from "./pages/orbat/Units";
import Members from "./pages/orbat/Members";
import Ranks from "./pages/orbat/Ranks";
import Positions from "./pages/orbat/Positions";
import Settings from "./pages/orbat/Settings";

export default function App() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-panel-muted">
        Loading…
      </div>
    );
  }

  if (!user) return <Login />;

  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/orbat/units" element={<Units />} />
        <Route path="/orbat/members" element={<Members />} />
        <Route path="/orbat/ranks" element={<Ranks />} />
        <Route path="/orbat/positions" element={<Positions />} />
        <Route path="/orbat/settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}
