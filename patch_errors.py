import os, sys

CO = "frontend/src/pages/Checkout.jsx"
SV = "backend/server.py"
done = []

# ---- Checkout.jsx: show what the server said, under the right field ----
if os.path.exists(CO):
    c = open(CO, encoding="utf-8").read()
    old = '    } catch {\n      toast.error("Could not start payment.");\n      setPaying(false);\n    }\n'
    if "const detail = err" in c:
        done.append("Checkout.jsx: already shows the server message")
    elif "validateTraveller" not in c:
        sys.exit("STOP: run patch_checkout.py first (Checkout.jsx has no field checks yet). Nothing was changed.")
    elif c.count(old) != 1:
        sys.exit("STOP: the 'Could not start payment' block was not found in Checkout.jsx (nothing was changed)")
    else:
        new = (
            "    } catch (err) {\n"
            "      const detail = err && err.response && err.response.data && err.response.data.detail;\n"
            "      const msg = typeof detail === \"string\" ? detail : \"Could not start payment.\";\n"
            "      toast.error(msg);\n"
            "      if (typeof detail === \"string\") {\n"
            "        const key = /city/i.test(detail) ? \"city\" : /address/i.test(detail) ? \"address\" : /email/i.test(detail) ? \"email\" : /mobile|phone/i.test(detail) ? \"phone\" : /name/i.test(detail) ? \"name\" : null;\n"
            "        if (key) {\n"
            "          setErrors((o) => ({ ...o, [key]: msg }));\n"
            "          const el = document.querySelector(`[data-testid=\"checkout-${key}\"]`);\n"
            "          if (el && el.focus) el.focus();\n"
            "        }\n"
            "      }\n"
            "      setPaying(false);\n"
            "    }\n"
        )
        open(CO, "w", encoding="utf-8").write(c.replace(old, new, 1))
        done.append("Checkout.jsx: server messages now show on screen")
else:
    sys.exit("STOP: " + CO + " not found. Run this from the repo root.")

# ---- server.py: name the wrong value in the message ----
if os.path.exists(SV):
    s = open(SV, encoding="utf-8").read()
    if "_check_traveller" not in s:
        done.append("server.py: no traveller check yet (run patch_server_check.py), skipped")
    else:
        oc = '        return "Please enter a valid city (a state is not a city)."\n'
        oa = '        return "Please enter the full address, with house number, street and area."\n    return ""\n'
        if "is a state, not a city" in s:
            done.append("server.py: messages already clear")
        elif s.count(oc) == 1 and s.count(oa) == 1:
            s = s.replace(oc, '        return (f"{city.title()} is a state, not a city. Please enter your city, for example Gurugram." if _is_state(city) else "Please enter a valid city name.")\n', 1)
            s = s.replace(oa, '        return ("That is a state. Please enter the full address, with house number, street and area." if _is_state(address) else "Please enter the full address, with house number, street and area.")\n    return ""\n', 1)
            open(SV, "w", encoding="utf-8").write(s)
            done.append("server.py: messages now say e.g. 'Rajasthan is a state, not a city'")
        else:
            sys.exit("STOP: server message lines not found (Checkout.jsx was already changed; run again after checking)")
print("OK:")
for d in done:
    print(" -", d)