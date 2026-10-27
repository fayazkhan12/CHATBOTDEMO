"""patch_hotel_live.py - shows LIVE hotel details on the hotel page: real photos, amenities,
places nearby and every room option with its real price. The chosen room is what gets booked.

Run from the repo root (the folder that contains `backend` and `frontend`):

    python patch_hotel_live.py

What it changes
  backend/hotel_live.py          NEW  reads the company hotel API and cleans it (supplier cost and markup never leave the server)
  backend/live_check.py          NEW  one command to see the live data and to check the API has not changed
  backend/server.py              +  search cards carry search id / hotel id / dates, new fields allowed in a booking, 3 wiring lines
  frontend/src/pages/Detail.jsx  the hotel page (photos, rooms, price, reserve)
  frontend/src/App.css           + styles for the new parts

Safe: if anything does not match, it stops and changes nothing. If something fails half way,
every file is put back. Running it twice is harmless.
"""
import base64
import hashlib
import os
import sys
import zlib

FILES = {
    "hotel_live.py": (
        "a0af2ac516291efa9646b493bd18f2955b4cb5ec484608aa2c5768eaf79ef486",
        """
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
""",
    ),
    "live_check.py": (
        "506bf572423632efce94c859b4ce566a6cee7687434299c49792ed0509731434",
        """
eNp9WG1z4jgS/s6vUPk+YO+CM2Fymz22uCt2Z6Yme1uZVDJ394HlPMIWoImxXJKAUDn++z0t2cYwMFSlYkvdrX59uuUgCO4Ms0vB
crkRbKmsyFnGLWfGyjxnsnCbZslL4Z7SJbczZZl4KUVqzT86ncd1weZardz2jKfPosjYXOWZ0CwshMi8fMNXgsWi2LArtqF/vFoX
eiN0NOx0GH7lzi5V4ZRJ0qVIn+Nyx87//sJ+57Jc6x67voHKO+O1KNS2xwaskIulNZdl9vtfDRa/kclzo1ipZWG9ubnghciYFmad
2++Jy1XKrVRFX2ZsMLi9ffsTLXLLBj/Ff7se3Ax+dkTFgt3+Nb79+XZw2+ncWZjPNaQYnMBz73/DlPd6qlYlL3Zs/HDXY6oUhffY
XGpjGd9wmfNZXgWtx0pujPAUvDBboTt2qdV6sTy431kjoUKqMh/OrZgZaQVbEytH4CAKCuzUmj2Mn56Y0uzD+O6PuHOv7JI4pWEz
pZ5F1oOnWa4WyBCsUZxFFneCIOi4MCTJfG3XWiQJk6tSaShcFMo6F5lOp17Ti5JrI5p3sytSqepXClH9rEz9pBtys2sWrVwJfzKy
V9BbfS6999x+JnLLPZHdlc4aTzIudj32Tqa2xz6VpCHPGxWX1pYvhzfydeJqBfm7BFknE3OW5IpnCbI6jFj/7+xeFWLoksXqnX+g
n1cPEpD9lTzH55c6Dd1SaMFGsDguuV3GmdQFohfW73xm6H8IF8scDo6iwwmIV0lF2xB/VbIISWCPBVR9QdRjZ/fioKGIDirTT84b
DvEijTVheUJBv5Yl2Hfb4iUVpWV3ztT3Wit9YKNsrZw3l0WW+DpIZBbOVLYbUkicK42tmJBZ95S15dqaqmruMrYuCGa+rIQxfCG+
sJAXTM2+ApoiZhVQ4RfGU6fFF0K1L1hUPXJQyo2rgB2Of2HSxpS5tQufsUxODCq55BpiD1p2bxAhUjVeCBuCISI/SSMLY3mRCmdG
j2WSNEFNC5cUnZZPW7SbmpAqsL3uhAe1tRQ7+OPE+Vqgzgq2mRzopo5gBQ21iP1qqLuH/T/ND0P8BeHkv8H0xyjo9lypxdl6VRqn
eZVTlexVvACSlOG1M3Ll7YG/fPxKmT4nrjBCD5PmEL66nCZUXRMo36Ot6dSbAORZGWi5zOMkk4uavfY2/juKICIcmkyb+EhL4XF7
wwsulfbIp7by5Loscyn0R9KWHOp2gUsNhTRPaF2f1jY472Zp245xMfVe0OsiTCG7sEOPGfFv7q1HIAeP1FAX36OWUcCpcA5Co/Hn
8FLCE0Qb4zEGxGtZhsEVdPyRBVdYu9pc+xR1XQcOGDlsi12eh0TWgFxI/XDkhNFTwpeCZz6kFF1wvjbGBXXngj+GlF+h46tXUZJR
70C8EOo3lCEoXwN0tyMObpGgAfW4Y0HFItq3RDj17wrQVIbE0iiEdcVtGJ3SUSSGLKxNPm+jb/ZRdEGQVgpJNGST14BnlGB4HvTo
AJlnWpAmb+rX8UI40ul+2pJQcJ/G0u6wGdzdB35z7ycCGhfCeXAdsydXYtRaqlYevpLDJ93K6O50T1FvL8JCrEYsBgRXVYf4+FSK
S2VI8ivCv79yIv0JV76WA1+4I1eynjfWXBqRwA0JSsGuTeg3DOaS0SnW6pjYw6raUUFUCqBs4bSzLaAhYEgdv0HeejJ07zQflWjs
Ijj0oqpErqt6OQADZd++qeWEJGleLIRPl1JhAGnVHsU7NrkQ5WE/2XJpWye1HEZFfNlfV68wbt9W8qK/WloTjtaeasPNZdjyklC6
oxHyCmNcLqxAeR0hygwj37Nb8WP36AySHgXG7VwITRUHxFeaJQbW2dpSuE6mRLS9lR/SLwVq6dKEitcxTL6BzGl0lPODGBgviibj
2av75+LQpbGlG+1RBBC7j3Cmhzqa8hiB5kL5gem4OxxM9JRbaZcVpo5pwQNrSJmh1nb0FsVrkUGGxgwPCEnzHtGcxtOzWM4pjSiK
c2FRD5mwcJYJedpjRyn0zm8cag5J1CNPeWyv4ccb5y5Po3qSjaktkJXea6nHbD5BUhQYlWwwpdb2eowjb2PmvI0lwGx67MtmATmm
Ew1gKhZY/+GwkQKlsBIcBwqPD7BGGSc0F+hWnlyuMOEYjACTaUTy2XiFeFopzDEdr5dbpPfwyGx3TFe4tZroRIubmD0SGrNGC+eO
roPo7pSEEtbjtokrzqNhr36bJucEMlJBUFnJJPTQK4IP71IP89PTAnGm99mrXk28E6eT4dubKf727H9+eaa4zrouFN1+d3g9aHZS
Giby3MH/MSMpRxSVVpOuxe0mh3ot7bYH5bZcU5Gc0Y/Uq3aHyK2tZ1fPbr5UeeXWgFTHaO4GFrd+ZPRhkDk9rgYQl6mEYafntyY/
4qXpOENmjq57DDdOusJxk0o5+oCrsYja4Qz+LB7fP/3rj8+kd+Dui33/HcEVAdqwu9lul9ye+3YQuJvFczVNEoyB3QhRewN1O1Ob
uqVUNfumzXRdzV4rjovM8TjVupE1FzG633uQImcagGGB9zwjxTRPrdA4kv0H9qstdtHPFIAzdRdXZpZq+wvuuRvcN1LNzbK6pa8a
d+I2GhubAZJiLcA9lwt4LxR08TGjQIsyx9QXHN2NwrHFnAewFu5+1GP/5vnaP0cnlyU/JPoZ0U+SY71YoyjtA73pMBMmxcxIqTpK
cBVLk6TH/DgE05I0h5RRw/zIt+8ODB9FXn6oSaPqrJhnWcKrQ8Kg3wckItLwOEdvGuFSCP9KjfRxGXr/6d37ZPxwl/w6fnrvZ/ZT
kvE/fx0/OpqPn54+e5qAkN0Mr2jE7WdiE8MOgJra8l2M1hlc1Kb1xaWlVeA/vnyHDVNrm7z+PPO9gzDRtljqDziXOWg07buhG3x2
V4qRpJtALeH65iKn7yVnuQYXmdzMdP6k7zP1qQPWjHOUTIv1Jn5zkZcwA2yoGUo2jDsKMGH1us5uAhvK1DJ2yUa89Vx10p9B1VyM
jz6WtJr+Sb+/eeOaenXZOtfYD3cx36GPSs7L/Pj584MrMxKFnW+7hp+rUrXOPbBiWkv9tzTkL0Ya8lkIzihOEsKTJNmjpWGhaVAt
jQZAKgBXTenmwiQh3EqSaiwk+BAv0oYezaLO/wE+Usaz
""",
    ),
    "Detail.jsx": (
        "3e91ed0a2a1d1551b8cd2bd60f36bacce26dff9e867d2773a18c961f794ecc85",
        """
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
""",
    ),
    "live.css": (
        "f88754e6e3e234ac41e5530a03f9c9a0593632a2bc985574b286ccdc5d822631",
        """
eNqtV+1q4zgU/d+nEDMsNEOV2mmSJg4L+x7Lssi2bGsqS0aSk3SHefe9kvwlx91mYAmYxrk69+vco9uH52+IszPFlTSU45wawrhG
jw0xWfW3/WWFvj0/rHOOTdXWqUY/UM50w8l7ggpOrydUkiZBhwb+qokqmUhQHDVXFKHYvZRnqgouL/iaINIaeUINyXMmSpxKY2Sd
oK01+zn6ABcWOQGIqDtyYbmpwIszrSgrK5OgfWS/dWhgfUKpVDlVWJGctdrHMQaQoIrlORVgRrK3UslW5AkSUtATylqlpUpQI5kw
VPVICdpAJlpyliOjiNANUVQYwGxIxgyUYH0IQ2d1CeF34cZR9NsYrv8m0+80M7hg8CazoZ3GeqZcZm8BXlJZE0AcHMbB738SxQiG
6G1Yv38xqqVf/gLzrhCZ5DarM1GPGBtK+BP6GhWv+z1dnT6CTAqZtRqfmWYpp9Z1azgTdFqLDwC9IZZFoalx9j2ykrIOqFMqlnfU
iTcjd7CRw5vxJBxspGaGSSCXopwY4OXpBgyeEFMN7wy1qbe1sCSwaKhmoibXx+gJxYVadazy7h2nCGelwAyOw5GMehIM1PIBfUCS
kW4OqWdOvN7N6uWKo42SooSy0Y39rEI2ekPdqoJkFIyKogCLWRuv5gkxUVHFzGpapoEs93R/PLZmGktx57FUXrGuSG7HKXKfF8hS
lSl5jHdQ3PhgH1DmdbwPg/O0ujBTMfF/sQoKLwNykBSgWkMn7I4G9Yin4uG+dJ3E9Awd170YjEHjcJw9DXoEL0YL87yoQvMhn3bd
l29jSzc81vEuqB+uiavbTHztE+dMQQyuAJ72HbVdgMB83CUQBYCC1Ha8CykM1uwfaEW8swdctYcyrV+CQ7q18hxQpIZ659Cxffq6
OUQQ9BRxs17C3PaYWcUa/UFWF2VzsM8unf1cJyYXhwWaJRMvuZ4MtR3PwzixQ7+Ox6N7+2mDtveNpg0Nl1LmdsRuQK0ibTZPaB/P
IL9G5JW85AHKhSixiHKEgI7bJxTNQdLt7iU6Bi1sFMvo/UwKlNEZUdFLt5sHmzV2VhCNLTMMXAX2GG7LjNqh8j28CcFL4axrh1D6
e9NfI90yRk04/yWcjkEeSVBitZUzDb+bd057uZhtPVG4kizdePsZKme37fjeasOKd1BjUCgB1HXVxCk1F0pFcHVOQ37xIf93jh3h
+/0LpBDlRFf0k4tqvrdN04Dt0fYouMUPN8EtSMH+s2CnDnRbg4d328T5Xez8XIbNMLprND1qMwTu9ljfw4DCjaKuKP05/Ub5bcsW
dwjfp3BTjZdkZ2l7uKcr91bP3pPTfSZwOEaxWda+QGA+070FQs66vhsqSc7zS2gTUHiQwb5D2Lco3k6H/ILPhLs2XvvLbm+37QVt
+vnwR01zRtDj1HgLHVqhHw8ITZbODzbKw+FmobSw49FwbTgcgn9auqmZWPeC7Nx5L1AG9IxwfCvLkOuMaSnR1JPzRjNmct1p68+H
fwEQMY6R
""",
    ),
}
OLD_DETAIL_SHA = "3ad36b586260e28477356d245103686869495089713ba7f1eea2bb6f93123e85"
CSS_MARK = "/* live-hotel-details (patch_live) */"

SERVER = os.path.join("backend", "server.py")
DETAIL = os.path.join("frontend", "src", "pages", "Detail.jsx")
CSS = os.path.join("frontend", "src", "App.css")
NEW_FILES = {"hotel_live.py": os.path.join("backend", "hotel_live.py"), "live_check.py": os.path.join("backend", "live_check.py")}


def stop(msg):
    print("STOP:", msg)
    print("Nothing was changed.")
    sys.exit(1)


def read_text(path):
    if not os.path.isfile(path):
        stop(path + " not found. Run this from the repo root (the folder that contains backend and frontend).")
    with open(path, "rb") as f:
        raw = f.read()
    bom = raw.startswith(b"\xef\xbb\xbf")
    try:
        text = (raw[3:] if bom else raw).decode("utf-8")
    except UnicodeDecodeError:
        stop(path + " is not UTF-8 text.")
    nl = "\r\n" if "\r\n" in text else "\n"
    return text.replace("\r\n", "\n"), nl, bom


def to_bytes(text, nl, bom):
    data = text.replace("\n", nl) if nl == "\r\n" else text
    return (b"\xef\xbb\xbf" if bom else b"") + data.encode("utf-8")


def swap(text, old, new, label):
    if text.count(old) != 1:
        stop("could not find %s exactly once in the file (found %d)." % (label, text.count(old)))
    return text.replace(old, new, 1)


def payload(name):
    sha, data = FILES[name]
    raw = zlib.decompress(base64.b64decode("".join(data.split())))
    if hashlib.sha256(raw).hexdigest() != sha:
        stop(name + " inside this patch is damaged (checksum mismatch). Download patch_hotel_live.py again.")
    return raw


def main():
    changes = []  # (path, bytes)
    notes = []

    # ---------------- server.py ----------------
    srv, nl, bom = read_text(SERVER)
    new_srv = srv

    keys_old = '    "cabin", "baggage", "nights", "price_token",\n]'
    keys_new = (
        '    "cabin", "baggage", "nights", "price_token",\n'
        '    "search_id", "hotel_id", "check_in", "check_out", "guests",\n'
        '    "recommendation_id", "room_name", "cancellation", "board",\n]'
    )
    if '"search_id", "hotel_id"' in new_srv:
        notes.append("server.py: booking fields already allowed")
    else:
        new_srv = swap(new_srv, keys_old, keys_new, "the _ITEM_KEYS list")

    ret_old = '        return {"items": out, "total": total, "page": page}\n'
    ret_new = (
        "        try:\n"
        "            nights = max(1, (date.fromisoformat(req.end_date) - date.fromisoformat(req.start_date)).days)\n"
        "        except ValueError:\n"
        "            nights = 1\n"
        "        for card in out:  # the hotel page needs these to load live photos, rooms and prices (patch_live)\n"
        '            card["search_id"] = sid\n'
        '            card["hotel_id"] = str(card["id"])[3:]\n'
        '            card["check_in"], card["check_out"] = req.start_date, req.end_date\n'
        '            card["nights"], card["guests"] = nights, req.travellers\n'
    ) + ret_old
    if 'card["search_id"] = sid' in new_srv:
        notes.append("server.py: search cards already carry the live ids")
    else:
        new_srv = swap(new_srv, ret_old, ret_new, "the end of _akbar_hotels")

    hook_old = "app.include_router(api)\n"
    hook_new = (
        "try:  # live hotel photos, rooms and prices (patch_live); an optional feature must never stop the API from starting\n"
        "    try:\n"
        "        import hotel_live as _hotel_live\n"
        "    except ImportError:  # the app was started from the repo root as backend.server\n"
        "        from backend import hotel_live as _hotel_live\n"
        "    _hotel_live.set_signer(_price_token)\n"
        "    app.include_router(_hotel_live.router)\n"
        "except Exception:\n"
        '    logger.exception("live hotel details are switched off")\n'
    ) + hook_old
    if "_hotel_live" in new_srv:
        notes.append("server.py: live router already wired")
    else:
        if "def _price_token(" not in new_srv:
            stop("this server.py has no _price_token (patch_price.py was not applied).")
        new_srv = swap(new_srv, hook_old, hook_new, "app.include_router(api)")
    try:
        compile(new_srv, SERVER, "exec")
    except SyntaxError as exc:
        stop("the patched server.py would not compile (%s). This is a bug in the patch." % exc)
    if new_srv != srv:
        changes.append((SERVER, to_bytes(new_srv, nl, bom)))

    # ---------------- Detail.jsx ----------------
    det, dnl, dbom = read_text(DETAIL)
    if "hotels/live" in det:
        notes.append("Detail.jsx: already the live version")
    else:
        if hashlib.sha256(det.encode("utf-8")).hexdigest() != OLD_DETAIL_SHA:
            stop("frontend/src/pages/Detail.jsx is not the version this patch was made for. Send me the current file.")
        changes.append((DETAIL, to_bytes(payload("Detail.jsx").decode("ascii"), dnl, dbom)))

    # ---------------- App.css ----------------
    css, cnl, cbom = read_text(CSS)
    if CSS_MARK in css:
        notes.append("App.css: styles already added")
    else:
        add = payload("live.css").decode("utf-8")
        changes.append((CSS, to_bytes(css.rstrip("\n") + "\n" + add, cnl, cbom)))

    # ---------------- new backend files ----------------
    for name, path in NEW_FILES.items():
        raw = payload(name)
        if os.path.isfile(path):
            with open(path, "rb") as f:
                if f.read() == raw:
                    notes.append(path + ": already up to date")
                    continue
        changes.append((path, raw))

    # ---------------- write all, or put everything back ----------------
    before = {}
    for path, _ in changes:
        before[path] = open(path, "rb").read() if os.path.isfile(path) else None
    try:
        for path, data in changes:
            with open(path, "wb") as f:
                f.write(data)
            print("wrote", path)
    except Exception as exc:  # restore the originals
        for path, old in before.items():
            if old is None:
                if os.path.isfile(path):
                    os.remove(path)
            else:
                with open(path, "wb") as f:
                    f.write(old)
        stop("could not write the files (%s). Everything was put back." % exc)

    for n in notes:
        print("note:", n)
    if not changes:
        print("Nothing to do - already applied.")
    print("\nDone. Next:")
    print("  1. (optional) cd backend  then  python live_check.py     to see the live data in the terminal")
    print("  2. git add -A")
    print('  3. git commit -m "Live hotel details: photos, amenities, rooms and real prices"')
    print("  4. git push        (Render deploys the API and the website; wait until both say Live)")


main()
