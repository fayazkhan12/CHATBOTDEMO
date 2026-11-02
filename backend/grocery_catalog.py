"""The demo grocery shelf: what the Blinkit-style store "sells".

Every item: id, name, unit, mrp, price, category, an emoji (no stock photos, so nothing can be a wrong picture) and the
other words people use for it (Hindi / Hinglish), so "doodh", "aloo" or "pyaaz" find the right thing.
These are DEMO products and prices; nothing is shipped and nothing is charged.
"""
from typing import Any, Dict, List

# (category id, category name, emoji, [(name, unit, mrp, price, "alias alias ...")])
_SHELF = [
    ("fruits-veg", "Fruits & Vegetables", "🥦", [
        ("Onion", "1 kg", 48, 39, "pyaaz pyaz kanda"), ("Potato", "1 kg", 45, 36, "aloo aalu batata"),
        ("Tomato", "500 g", 34, 28, "tamatar tamater"), ("Green Chilli", "100 g", 18, 14, "hari mirch mirchi"),
        ("Coriander Leaves", "100 g", 15, 12, "dhania dhaniya"), ("Ginger", "100 g", 20, 16, "adrak"),
        ("Garlic", "100 g", 24, 19, "lehsun lasun"), ("Lemon", "4 pcs", 20, 16, "nimbu nimboo"),
        ("Cucumber", "500 g", 30, 24, "kheera kakdi"), ("Carrot", "500 g", 36, 29, "gajar"),
        ("Cauliflower", "1 pc", 40, 32, "gobhi phool gobi"), ("Spinach", "250 g", 25, 20, "palak"),
        ("Banana", "6 pcs", 48, 40, "kela kele"), ("Apple Shimla", "4 pcs", 160, 139, "seb"),
        ("Pomegranate", "2 pcs", 150, 129, "anar"), ("Papaya", "1 pc", 60, 49, "papita"),
        ("Green Peas", "500 g", 70, 58, "matar mutter"), ("Capsicum", "250 g", 36, 29, "shimla mirch"),
        ("Okra (Bhindi)", "250 g", 32, 26, "bhindi lady finger"), ("Brinjal", "500 g", 38, 30, "baingan eggplant"),
        ("Cabbage", "1 pc", 35, 28, "patta gobhi band gobhi"), ("Mango", "1 kg", 120, 99, "aam"),
        ("Grapes", "500 g", 80, 69, "angur"), ("Mint Leaves", "50 g", 15, 12, "pudina"),
    ]),
    ("dairy-eggs", "Dairy & Eggs", "🥛", [
        ("Full Cream Milk", "1 L", 74, 72, "doodh dudh milk"), ("Toned Milk", "500 ml", 29, 28, "doodh dudh milk"),
        ("Fresh Curd", "400 g", 45, 40, "dahi curd yogurt"), ("Paneer", "200 g", 95, 85, "cottage cheese"),
        ("Salted Butter", "100 g", 58, 56, "makhan butter"), ("Cheese Slices", "10 slices", 140, 125, "cheese"),
        ("Eggs", "6 pcs", 60, 54, "ande anda egg"), ("Brown Eggs", "12 pcs", 140, 124, "ande anda egg"),
        ("Condensed Milk", "400 g", 140, 128, "milkmaid"), ("Mozzarella Cheese", "200 g", 150, 135, "pizza cheese"),
        ("Lassi", "200 ml", 25, 22, "chaas chhach lassi"), ("Pure Ghee", "500 ml", 340, 315, "ghee desi ghee"),
    ]),
    ("bread-bakery", "Bread & Bakery", "🍞", [
        ("White Bread", "400 g", 45, 40, "bread pav double roti"), ("Brown Bread", "400 g", 55, 48, "bread atta bread"),
        ("Pav", "6 pcs", 30, 28, "ladi pav bun"), ("Burger Buns", "4 pcs", 45, 40, "bun"),
        ("Rusk", "300 g", 60, 52, "toast rusk"), ("Cream Biscuits", "100 g", 20, 18, "biscuit biscuits"),
        ("Digestive Biscuits", "250 g", 65, 58, "biscuit biscuits"), ("Cake Slice Chocolate", "1 pc", 30, 28, "cake"),
    ]),
    ("atta-rice-dal", "Atta, Rice & Dal", "🌾", [
        ("Wheat Flour (Atta)", "5 kg", 280, 249, "atta aata gehu gehun flour"), ("Basmati Rice", "1 kg", 140, 119, "chawal chaval rice"),
        ("Sona Masoori Rice", "5 kg", 380, 349, "chawal chaval rice"), ("Toor Dal", "1 kg", 190, 169, "arhar tuvar dal daal"),
        ("Moong Dal", "500 g", 100, 89, "mung dal daal"), ("Chana Dal", "500 g", 80, 72, "dal daal"),
        ("Masoor Dal", "500 g", 70, 62, "dal daal"), ("Rajma", "500 g", 120, 105, "rajmah"),
        ("Kabuli Chana", "500 g", 110, 98, "chole chhole chana"), ("Besan", "500 g", 70, 62, "gram flour"),
        ("Poha", "500 g", 55, 48, "chivda"), ("Suji (Rava)", "500 g", 45, 40, "sooji rava semolina"),
    ]),
    ("oil-masala", "Oil, Ghee & Masala", "🧂", [
        ("Sunflower Oil", "1 L", 165, 149, "tel oil refined"), ("Mustard Oil", "1 L", 190, 175, "sarson tel oil"),
        ("Salt", "1 kg", 28, 25, "namak"), ("Sugar", "1 kg", 52, 47, "cheeni chini shakkar"),
        ("Turmeric Powder", "100 g", 34, 30, "haldi"), ("Red Chilli Powder", "100 g", 48, 42, "lal mirch mirchi"),
        ("Coriander Powder", "100 g", 36, 32, "dhania dhaniya"), ("Garam Masala", "50 g", 55, 49, "masala"),
        ("Jeera (Cumin)", "100 g", 70, 62, "zeera jira"), ("Tea Leaves (Chai Patti)", "250 g", 140, 125, "chai chay tea"),
        ("Coffee Powder", "100 g", 150, 135, "coffee kofi"),
    ]),
    ("snacks", "Snacks & Munchies", "🍟", [
        ("Potato Chips Classic", "52 g", 20, 20, "wafers chips"), ("Masala Chips", "52 g", 20, 20, "wafers chips"),
        ("Namkeen Bhujia", "200 g", 55, 50, "sev bhujia namkin"), ("Aloo Bhujia", "200 g", 55, 50, "namkin"),
        ("Popcorn Butter", "60 g", 30, 28, "pop corn"), ("Roasted Peanuts", "200 g", 50, 44, "moongfali mungfali"),
        ("Dark Chocolate", "50 g", 90, 80, "chocolate choclate"), ("Milk Chocolate Bar", "40 g", 40, 40, "chocolate choclate"),
        ("Almonds", "200 g", 220, 195, "badam dry fruits"), ("Cashews", "200 g", 260, 230, "kaju dry fruits"),
        ("Cup Noodles", "70 g", 55, 50, "noodles"), ("Corn Chips", "60 g", 20, 20, "kurkure nachos chips"),
        ("Makhana", "100 g", 120, 105, "fox nuts"), ("Mixed Dry Fruits", "250 g", 290, 259, "kishmish akhrot"),
    ]),
    ("cold-drinks", "Cold Drinks & Juices", "🥤", [
        ("Cola", "750 ml", 40, 38, "cold drink soft drink coke pepsi"), ("Lemon Soda", "750 ml", 40, 38, "cold drink soda sprite"),
        ("Orange Juice", "1 L", 120, 105, "juice jus"), ("Mango Drink", "600 ml", 40, 38, "aam juice jus frooti"),
        ("Packaged Water", "1 L", 20, 20, "pani paani water bottle"), ("Coconut Water", "200 ml", 40, 38, "nariyal pani"),
        ("Energy Drink", "250 ml", 125, 115, "redbull"), ("Iced Tea Peach", "500 ml", 40, 38, "ice tea"),
    ]),
    ("instant", "Instant & Packaged Food", "🍜", [
        ("Instant Noodles Masala", "4 pack", 56, 52, "maggi noodles"), ("Pasta", "500 g", 90, 79, "macaroni"),
        ("Tomato Ketchup", "500 g", 110, 95, "sauce ketchup"), ("Corn Flakes", "475 g", 190, 169, "cereal breakfast"),
        ("Oats", "1 kg", 190, 170, "oatmeal breakfast"), ("Peanut Butter", "340 g", 190, 165, "butter spread"),
        ("Mixed Fruit Jam", "500 g", 150, 130, "jam jelly"), ("Honey", "250 g", 140, 125, "shahad shehad"),
    ]),
    ("personal-care", "Personal Care", "🧴", [
        ("Bath Soap", "3 x 100 g", 130, 115, "sabun soap"), ("Shampoo", "340 ml", 260, 230, "shampoo baal"),
        ("Toothpaste", "200 g", 110, 99, "paste colgate"), ("Toothbrush", "2 pcs", 70, 62, "brush"),
        ("Face Wash", "100 ml", 190, 165, "facewash"), ("Hand Wash", "250 ml", 99, 85, "handwash sanitizer"),
        ("Sanitary Pads", "20 pcs", 190, 170, "pads"), ("Deodorant", "150 ml", 220, 185, "deo perfume"),
    ]),
    ("frozen", "Ice Cream & Frozen", "🍦", [
        ("Vanilla Ice Cream", "500 ml", 190, 169, "icecream ice cream"), ("Chocolate Ice Cream Cup", "100 ml", 40, 40, "icecream ice cream kulfi"),
        ("Frozen Green Peas", "500 g", 100, 85, "matar"), ("Frozen Paratha", "5 pcs", 95, 84, "parantha"),
        ("Frozen French Fries", "420 g", 160, 139, "fries aloo"), ("Ice Cubes Tray", "1 pc", 30, 28, "baraf"),
    ]),
    ("home-cleaning", "Home & Cleaning", "🧹", [
        ("Dishwash Liquid", "500 ml", 110, 95, "bartan vim"), ("Detergent Powder", "1 kg", 130, 115, "surf washing powder kapde"),
        ("Floor Cleaner", "1 L", 190, 165, "phenyl pocha"), ("Toilet Cleaner", "500 ml", 90, 80, "harpic"),
        ("Garbage Bags", "30 pcs", 90, 79, "dustbin bag"), ("Tissue Paper", "2 rolls", 80, 70, "tissue"),
        ("Aluminium Foil", "9 m", 70, 62, "foil"), ("Matchbox", "10 pcs", 20, 18, "maachis"),
    ]),
    ("baby-pet", "Baby & Pet Care", "🍼", [
        ("Baby Diapers M", "22 pcs", 520, 449, "diaper"), ("Baby Wipes", "72 pcs", 190, 165, "wipes"),
        ("Infant Cereal", "300 g", 260, 235, "cerelac baby food"), ("Dog Food Chicken", "1 kg", 380, 340, "kutta pet food"),
        ("Cat Food Tuna", "400 g", 250, 225, "billi pet food"),
    ]),
]

FREE_DELIVERY_FROM = 199
DELIVERY_FEE = 25
HANDLING_FEE = 4
SMALL_CART_FEE = 20          # on carts under 99 rupees
MIN_ORDER = 49
MAX_QTY = 10
MAX_LINES = 40
COUPONS = {"DEMO50": {"off": 50, "min": 399, "text": "Rs 50 off on orders of Rs 399 or more"},
           "FIRST30": {"off": 30, "min": 199, "text": "Rs 30 off on orders of Rs 199 or more"}}


def _slug(s: str) -> str:
    out = []
    for ch in s.lower():
        out.append(ch if ch.isalnum() else "-")
    return "-".join(p for p in "".join(out).split("-") if p)


def _build() -> Dict[str, Any]:
    cats: List[Dict[str, Any]] = []
    items: List[Dict[str, Any]] = []
    for cid, cname, emoji, rows in _SHELF:
        cats.append({"id": cid, "name": cname, "emoji": emoji})
        for name, unit, mrp, price, aliases in rows:
            items.append({"id": f"g-{_slug(name)}", "name": name, "unit": unit, "mrp": mrp, "price": price, "category": cid,
                          "emoji": emoji if cid not in _EMOJI else _EMOJI[cid].get(name, emoji), "aliases": aliases})
    return {"categories": cats, "items": items}


# a few items look better with their own picture
_EMOJI: Dict[str, Dict[str, str]] = {
    "fruits-veg": {"Onion": "🧅", "Potato": "🥔", "Tomato": "🍅", "Green Chilli": "🌶️", "Coriander Leaves": "🌿", "Ginger": "🫚",
                   "Garlic": "🧄", "Lemon": "🍋", "Cucumber": "🥒", "Carrot": "🥕", "Cauliflower": "🥦", "Spinach": "🥬",
                   "Banana": "🍌", "Apple Shimla": "🍎", "Pomegranate": "🍎", "Papaya": "🍈", "Green Peas": "🫛", "Capsicum": "🫑"},
    "dairy-eggs": {"Eggs": "🥚", "Brown Eggs": "🥚", "Salted Butter": "🧈", "Cheese Slices": "🧀", "Pure Ghee": "🫙"},
    "bread-bakery": {"Cake Slice Chocolate": "🍰", "Cream Biscuits": "🍪", "Digestive Biscuits": "🍪", "Burger Buns": "🍔"},
    "snacks": {"Dark Chocolate": "🍫", "Milk Chocolate Bar": "🍫", "Popcorn Butter": "🍿", "Roasted Peanuts": "🥜", "Almonds": "🌰", "Cashews": "🌰"},
    "cold-drinks": {"Packaged Water": "💧", "Coconut Water": "🥥", "Orange Juice": "🧃", "Mango Drink": "🧃"},
    "instant": {"Honey": "🍯", "Pasta": "🍝", "Cup Noodles": "🍜"},
}

_BUILT = _build()
CATEGORIES: List[Dict[str, Any]] = _BUILT["categories"]
ITEMS: List[Dict[str, Any]] = _BUILT["items"]
BY_ID: Dict[str, Dict[str, Any]] = {i["id"]: i for i in ITEMS}


def public(item: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in item.items() if k != "aliases"}
