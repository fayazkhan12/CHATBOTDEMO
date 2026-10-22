import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider } from "./lib/auth";
import Navbar from "./components/Navbar";
import AIConcierge from "./components/AIConcierge";
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

function Shell() {
  const location = useLocation();
  const isAgentHome = location.pathname === "/";
  return (
    <>
      <Navbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/search" element={<Results />} />
        <Route path="/detail/:service/:id" element={<Detail />} />
        <Route path="/checkout/:bookingId" element={<Checkout />} />
        <Route path="/booking/:bookingId" element={<BookingConfirm />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/login" element={<Login />} />
        <Route path="/trip/:shareId" element={<TripShare />} />
      </Routes>
      {!isAgentHome && <AIConcierge />}
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
