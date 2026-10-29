import { BrowserRouter, Route, Routes, useNavigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "./lib/auth";
import Navbar from "./components/Navbar";
import Home from "./pages/Home";
import Results from "./pages/Results";
import Detail from "./pages/Detail";
import Checkout from "./pages/Checkout";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import AuthCallback from "./pages/AuthCallback";
import BookingConfirm from "./pages/BookingConfirm";
import TripShare from "./pages/TripShare";
import "./App.css";
import GlobalVoice from "./lib/GlobalVoice";

function NotFound() {
  const navigate = useNavigate();
  return (
    <div className="empty-state not-found" data-testid="not-found-page">
      <h2>Page not found</h2>
      <p>This page does not exist or has moved.</p>
      <button className="btn-primary" onClick={() => navigate("/")} data-testid="not-found-home">Back to home</button>
    </div>
  );
}

function Shell() {
  return (
    <>
      <Navbar />
      <GlobalVoice />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Results />} />
        <Route path="/detail/:service/:id" element={<Detail />} />
        <Route path="/checkout/:bookingId" element={<Checkout />} />
        <Route path="/booking/:bookingId" element={<BookingConfirm />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/login" element={<Login />} />
        <Route path="/trip/:shareId" element={<TripShare />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </>
  );
}

function AppRouter() {
  // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
  if (typeof window !== "undefined" && window.location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return <Shell />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppRouter />
        <Toaster richColors position="top-right" theme="dark" />
      </BrowserRouter>
    </AuthProvider>
  );
}
