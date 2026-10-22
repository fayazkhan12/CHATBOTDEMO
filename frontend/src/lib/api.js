import axios from "axios";

export const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

export const http = axios.create({ baseURL: API, withCredentials: true });

http.interceptors.request.use((config) => {
  const token = localStorage.getItem("dw_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

export const loadRazorpay = () =>
  new Promise((resolve) => {
    if (window.Razorpay) return resolve(true);
    const s = document.createElement("script");
    s.src = "https://checkout.razorpay.com/v1/checkout.js";
    s.onload = () => resolve(true);
    s.onerror = () => resolve(false);
    document.body.appendChild(s);
  });
