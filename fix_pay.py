p = "frontend/src/pages/Checkout.jsx"
s = open(p, encoding="utf-8").read()
a = "      if (!order.razorpay_order_id) {"
assert a in s
s = s.replace(a, "      const bid = order.booking_id || bookingId;\n" + a, 1)
h, t = s.split("const bid = order.booking_id || bookingId;", 1)
k = t.index("new window.Razorpay")
m, r = t[:k], t[k:]
m = m.replace("booking_id: bookingId", "booking_id: bid")
m = m.replace("/booking/${bookingId}", "/booking/${bid}")
m = m.replace("Booking ${bookingId}", "Booking ${bid}")
open(p, "w", encoding="utf-8").write(h + "const bid = order.booking_id || bookingId;" + m + r)

q = "backend/server.py"
x = open(q, encoding="utf-8").read()
b = "    if not hmac.compare_digest(expected, body.razorpay_signature):"
assert b in x
c = '    if booking.get("razorpay_order_id") != body.razorpay_order_id:\n        raise HTTPException(status_code=400, detail="Order mismatch")\n'
x = x.replace(b, c + b, 1)
open(q, "w", encoding="utf-8").write(x)
print("OK: 2 files patched")