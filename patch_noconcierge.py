import re, sys

P = "frontend/src/App.js"
try:
    a = open(P, encoding="utf-8").read()
except OSError:
    sys.exit("STOP: " + P + " not found. Run this from the repo root (D:\\projects\\destinoway-chatbot-demo).")

if "AIConcierge" not in a:
    sys.exit("Already removed. Nothing to do.")

imp = re.compile(r'^[ \t]*import\s+AIConcierge\s+from\s+["\'][^"\']+["\'];?[ \t]*\n', re.M)
use = re.compile(r'^[ \t]*<AIConcierge\b[^>]*/>[ \t]*\n', re.M)
if len(imp.findall(a)) != 1 or len(use.findall(a)) != 1:
    sys.exit("STOP: expected 1 import and 1 <AIConcierge /> line in App.js (nothing was changed)")
a = imp.sub("", a, count=1)
a = use.sub("", a, count=1)
if "AIConcierge" in a:
    sys.exit("STOP: AIConcierge is still mentioned in App.js (nothing was changed)")
open(P, "w", encoding="utf-8").write(a)
print("OK: old concierge chat button removed from App.js")