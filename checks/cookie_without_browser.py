"""Why the session answers Google's cookie-consent form first.

    python checks/cookie_without_browser.py

Asks for the gallery of the first place before and after submitting "Reject all" on the consent page.
Before: Google returns only the Street View item. After: the photos. The cookie that makes the
difference is `__Secure-ENID`; the one Google hands out before the form is answered does not work.
"""
import html
import http.cookiejar
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gbp_parser import maps_client  # noqa: E402
from gbp_parser.__main__ import load_places  # noqa: E402

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
place = load_places()[0]
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
opener.addheaders = [("User-Agent", USER_AGENT), ("Accept-Language", "en-US,en;q=0.9")]


def gallery(label):
    body = maps_client._request_body(place["fid"], place["mid"], None)
    request = urllib.request.Request(
        "https://www.google.com" + maps_client.RPC_URL, data=body.encode(),
        headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"})
    with opener.open(request, timeout=30) as response:
        data = maps_client._payload({"status": response.status, "url": response.url,
                                     "text": response.read().decode("utf-8")})
    print(f"{label}: cookies {sorted(c.name for c in jar)} -> total = {data[1]}, photos in the answer = {len(data[0] or [])}")


def attribute(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html.unescape(match.group(1)) if match else None


with opener.open("https://www.google.com/maps?hl=en", timeout=30) as response:
    page, landed = response.read().decode("utf-8", "replace"), response.url
print("opened Maps, landed on:", landed[:70])
gallery("1. before answering the consent form")

if "consent.google.com" in landed:
    for action, inner in re.findall(r'<form[^>]*\saction="([^"]+)"[^>]*>(.*?)</form>', page, re.S):
        fields = {attribute(tag, "name"): attribute(tag, "value") or ""
                  for tag in re.findall(r"<input[^>]*>", inner) if attribute(tag, "name")}
        if fields.get("set_eom") == "true":                     # the "Reject all" form
            with opener.open(html.unescape(action), data=urllib.parse.urlencode(fields).encode(), timeout=30) as r:
                r.read()
                print("sent 'Reject all', landed on:", r.url[:70])
            break
    else:
        print("no 'Reject all' form found on the consent page")
    gallery("2. after 'Reject all'               ")

with opener.open(place["maps_url"] + "?hl=en", timeout=30) as response:
    response.read()
gallery("3. after also opening the place page")
