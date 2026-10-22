import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { useAuth } from "../lib/auth";

// Backend errors can be a string or a list of validation errors; always return plain text.
const errText = (err, fallback) => {
  const d = err?.response?.data?.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return typeof d === "string" ? d : fallback;
};

export default function Login() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const { loginEmail, signupEmail, requestOtp, verifyOtp } = useAuth();

  const [method, setMethod] = useState("otp");       // "otp" | "password"
  const [channel, setChannel] = useState("email");   // "email" | "phone"
  const [step, setStep] = useState(1);               // 1 = enter email/phone, 2 = enter code
  const [mode, setMode] = useState(params.get("mode") === "signup" ? "signup" : "login");
  const [identifier, setIdentifier] = useState("");
  const [code, setCode] = useState("");
  const [cooldown, setCooldown] = useState(0);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (cooldown <= 0) return undefined;
    const t = setTimeout(() => setCooldown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [cooldown]);

  const done = () => navigate(params.get("redirect") || "/dashboard");

  const sendOtp = async (e) => {
    e?.preventDefault();
    setBusy(true);
    try {
      await requestOtp(channel, identifier);
      setStep(2);
      setCode("");
      setCooldown(60);
      toast.success("OTP bhej diya gaya");
    } catch (err) {
      toast.error(errText(err, "OTP nahi bhej paye"));
    } finally {
      setBusy(false);
    }
  };

  const checkOtp = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await verifyOtp(channel, identifier, code);
      toast.success("Welcome!");
      done();
    } catch (err) {
      toast.error(errText(err, "OTP galat hai"));
    } finally {
      setBusy(false);
    }
  };

  const submitPassword = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") {
        await loginEmail(form.email, form.password);
        toast.success("Welcome back!");
      } else {
        if (!form.name) { toast.error("Please enter your name"); return; }
        await signupEmail(form.name, form.email, form.password);
        toast.success("Account created!");
      }
      done();
    } catch (err) {
      toast.error(errText(err, "Could not sign in"));
    } finally {
      setBusy(false);
    }
  };

  const pickChannel = (c) => { setChannel(c); setIdentifier(""); setCode(""); setStep(1); };

  return (
    <div className="auth-page">
      <div className="auth-card" data-testid="auth-card">
        <h1>
          {method === "otp" ? "Login with OTP" : mode === "login" ? "Welcome back" : "Create your DestinoWay account"}
        </h1>
        <p>Save trips, manage bookings, and get a personal concierge.</p>

        <div className="auth-switch">
          <button type="button" className={method === "otp" ? "active" : ""} onClick={() => { setMethod("otp"); setStep(1); }} data-testid="switch-otp">OTP</button>
          <button type="button" className={method === "password" ? "active" : ""} onClick={() => setMethod("password")} data-testid="switch-password">Password</button>
        </div>

        {method === "otp" ? (
          <>
            <div className="auth-switch">
              <button type="button" className={channel === "email" ? "active" : ""} onClick={() => pickChannel("email")} data-testid="channel-email">Email</button>
              <button type="button" className={channel === "phone" ? "active" : ""} onClick={() => pickChannel("phone")} data-testid="channel-phone">Phone</button>
            </div>

            {step === 1 ? (
              <form className="auth-form" onSubmit={sendOtp}>
                <input
                  type={channel === "email" ? "email" : "tel"}
                  placeholder={channel === "email" ? "Email" : "Mobile (10 digit ya +91...)"}
                  value={identifier}
                  onChange={(e) => setIdentifier(e.target.value)}
                  required
                  data-testid="otp-identifier"
                />
                <button className="auth-submit" type="submit" disabled={busy} data-testid="otp-send">
                  {busy ? "Please wait…" : "Send OTP"}
                </button>
              </form>
            ) : (
              <form className="auth-form" onSubmit={checkOtp}>
                <small>{identifier} par 6-digit OTP bheja gaya hai</small>
                <input
                  inputMode="numeric"
                  maxLength={6}
                  placeholder="------"
                  autoComplete="one-time-code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                  required
                  data-testid="otp-code"
                />
                <button className="auth-submit" type="submit" disabled={busy || code.length !== 6} data-testid="otp-verify">
                  {busy ? "Please wait…" : "Verify & continue"}
                </button>
                <button type="button" className="btn-ghost" disabled={cooldown > 0 || busy} onClick={sendOtp} data-testid="otp-resend">
                  {cooldown > 0 ? `Resend in ${cooldown}s` : "Resend OTP"}
                </button>
                <button type="button" className="btn-ghost" onClick={() => { setStep(1); setCode(""); }}>
                  Change {channel}
                </button>
              </form>
            )}
          </>
        ) : (
          <>
            <div className="auth-switch">
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")} data-testid="switch-login">Log in</button>
              <button type="button" className={mode === "signup" ? "active" : ""} onClick={() => setMode("signup")} data-testid="switch-signup">Sign up</button>
            </div>
            <form className="auth-form" onSubmit={submitPassword}>
              {mode === "signup" && (
                <input placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="auth-name" />
              )}
              <input type="email" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required data-testid="auth-email" />
              <input type="password" placeholder="Password (min 8 characters)" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required minLength={8} data-testid="auth-password" />
              <button className="auth-submit" type="submit" disabled={busy} data-testid="auth-submit">
                {busy ? "Please wait…" : mode === "login" ? "Log in" : "Create account"}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}
