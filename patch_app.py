import re, sys

APP = "frontend/src/App.js"
GV = "frontend/src/lib/GlobalVoice.jsx"
try:
    a = open(APP, encoding="utf-8").read()
    g = open(GV, encoding="utf-8").read()
except OSError as e:
    sys.exit("STOP: " + str(e) + " (run this from the repo root, D:\\projects\\destinoway-chatbot-demo)")


def swap(text, old, new, label):
    if text.count(old) != 1:
        sys.exit("STOP: " + label + " not found (nothing was changed)")
    return text.replace(old, new)


if "AIConcierge" in a:
    a = swap(a, 'import AIConcierge from "./components/AIConcierge";\n', "", "AIConcierge import")
    a = swap(a, "      {!isAgentHome && <AIConcierge />}\n", "", "AIConcierge line")
    # these two only existed to hide the old widget on the chat page
    a = swap(a, "  const location = useLocation();\n  const isAgentHome = location.pathname === \"/\";\n", "", "isAgentHome lines")
    a = swap(a, "import { BrowserRouter, Route, Routes, useLocation } from", "import { BrowserRouter, Route, Routes } from", "react-router import")
    if "AIConcierge" in a or "isAgentHome" in a or "useLocation" in a:
        sys.exit("STOP: something is still left over in App.js (nothing was changed)")
    removed = True
else:
    removed = False

m = re.search(r'"bookings": null', g)
fixed = False
if m:
    g = g.replace('"bookings": null', '"bookings": "/dashboard"', 1)
    fixed = True

if not removed and not fixed:
    sys.exit("Already applied. Nothing to do.")
open(APP, "w", encoding="utf-8").write(a)
open(GV, "w", encoding="utf-8").write(g)
print("OK:", "old concierge button removed" if removed else "concierge already gone",
      "| my bookings opens /dashboard" if fixed else "| bookings path already set")