import re, sys

P = "frontend/src/pages/Checkout.jsx"
CSS = "frontend/src/App.css"
try:
    c = open(P, encoding="utf-8").read()
    css = open(CSS, encoding="utf-8").read()
except OSError as e:
    sys.exit("STOP: " + str(e) + " (run this from the repo root, D:\\projects\\destinoway-chatbot-demo)")
if "validateTraveller" in c:
    sys.exit("Already applied. Nothing to do.")
if not __import__("os").path.exists("frontend/src/lib/validate.js"):
    sys.exit("STOP: frontend/src/lib/validate.js is missing. Run patch_validate.py first.")


def swap(text, old, new, label):
    if text.count(old) != 1:
        sys.exit("STOP: " + label + " not found (nothing was changed)")
    return text.replace(old, new)


# a terminal line-wrap once glued two attributes together
c = c.replace("requireddata-testid", "required data-testid")

imports = list(re.finditer(r"^import .*$", c, re.M))
if not imports:
    sys.exit("STOP: no imports found in Checkout.jsx (nothing was changed)")
last = imports[-1]
c = c[:last.end()] + '\nimport { validateTraveller } from "../lib/validate";' + c[last.end():]

form_line = re.search(r"^  const \[form, setForm\] = useState\(.*\);\n", c, re.M)
if not form_line:
    sys.exit("STOP: form state line not found (nothing was changed)")
helpers = (
    "  const [errors, setErrors] = useState({});\n"
    "  // re-check the fields that are showing an error while the user fixes them\n"
    "  useEffect(() => {\n"
    "    setErrors((old) => {\n"
    "      if (!Object.keys(old).length) return old;\n"
    "      const now = validateTraveller(form);\n"
    "      const next = {};\n"
    "      Object.keys(old).forEach((k) => { if (now[k]) next[k] = now[k]; });\n"
    "      return next;\n"
    "    });\n"
    "  }, [form]);\n"
    "  const check = (k) => setErrors((old) => {\n"
    "    const msg = validateTraveller(form)[k];\n"
    "    const next = { ...old };\n"
    "    if (msg) next[k] = msg; else delete next[k];\n"
    "    return next;\n"
    "  });\n"
    "  const bad = (k) => (errors[k] ? <small className=\"field-error\" role=\"alert\">{errors[k]}</small> : null);\n"
)
c = c[:form_line.end()] + helpers + c[form_line.end():]

c = swap(c, '    if (!form.name || !form.email || !form.phone) { toast.error("Please fill all details"); return; }\n',
         '    const found = validateTraveller(form);\n'
         '    setErrors(found);\n'
         '    const firstBad = Object.keys(found)[0];\n'
         '    if (firstBad) {\n'
         '      toast.error(found[firstBad]);\n'
         '      const el = document.querySelector(`[data-testid="checkout-${firstBad}"]`);\n'
         '      if (el && el.focus) el.focus();\n'
         '      return;\n'
         '    }\n', "the 'fill all details' check")

c = swap(c, '<form className="checkout-form" onSubmit={pay}>', '<form className="checkout-form" onSubmit={pay} noValidate>', "form tag")

pat = re.compile(r'data-testid="checkout-(name|email|phone|city|address)"\s*/>')
if len(pat.findall(c)) != 5:
    sys.exit("STOP: expected 5 checkout inputs, found %d (nothing was changed)" % len(pat.findall(c)))
c = pat.sub(lambda m: 'onBlur={() => check("%s")} aria-invalid={!!errors.%s} data-testid="checkout-%s"/>{bad("%s")}' % ((m.group(1),) * 4), c)

css = css.rstrip("\n") + (
    "\n.field-error { display: block; margin-top: 6px; color: #c62828; font-size: 12.5px; line-height: 1.35; }\n"
    ".checkout-form input[aria-invalid=\"true\"] { border-color: #c62828 !important; }\n"
)
open(P, "w", encoding="utf-8").write(c)
open(CSS, "w", encoding="utf-8").write(css)
print("OK: checkout form now checks every field (typed or spoken) and shows the reason")