import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { api, clearAuthToken, LoginResponse, Me, setAuthToken } from "./api";

interface AuthState {
  user: Me | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthState>({
  user: null,
  loading: true,
  login: async () => {},
  refresh: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    try {
      const me = await api.get<Me>("/api/auth/me");
      setUser(me);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function login(username: string, password: string) {
    const result = await api.post<LoginResponse>("/api/auth/login", {
      username,
      password,
    });
    setAuthToken(result.token);
    setUser(result.user);
  }

  async function logout() {
    try {
      await api.post("/api/auth/logout");
    } finally {
      clearAuthToken();
      setUser(null);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, refresh, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
