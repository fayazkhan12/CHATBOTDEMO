import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { http } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const { data } = await http.get("/auth/me");
      setUser(data);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const loginEmail = async (email, password) => {
    const { data } = await http.post("/auth/login", { email, password });
    localStorage.setItem("dw_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const signupEmail = async (name, email, password) => {
    const { data } = await http.post("/auth/signup", { name, email, password });
    localStorage.setItem("dw_token", data.token);
    setUser(data.user);
    return data.user;
  };

  // OTP login: step 1 sends the code, step 2 verifies it and logs the user in.
  const requestOtp = (channel, identifier) =>
    http.post("/auth/otp/request", { channel, identifier });

  const verifyOtp = async (channel, identifier, code, name) => {
    const { data } = await http.post("/auth/otp/verify", { channel, identifier, code, name });
    localStorage.setItem("dw_token", data.token);
    setUser(data.user);
    return data.user;
  };

  const logout = async () => {
    try { await http.post("/auth/logout"); } catch { /* noop */ }
    localStorage.removeItem("dw_token");
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, refresh, loginEmail, signupEmail, requestOtp, verifyOtp, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => useContext(AuthContext);
