"""The requests Google Maps itself makes to show a place: its card and its photo gallery.

This is NOT the official Business Profile API. These are the internal calls behind google.com/maps.
Plain HTTPS requests: no browser and no Google login.

Google returns an empty gallery until the session has answered its cookie-consent form, so a session
starts by opening Maps and submitting "Reject all" (checks/cookie_without_browser.py shows the effect).
"""
import html
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

GOOGLE = "https://www.google.com"
RPC_URL = "/maps/_/MapsWizUi/data/batchexecute?rpcids=hspqX&hl=en&rt=c"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36")
TIMEOUT = 30
ATTEMPTS = 3
# Google returns at most ~80 items per page whatever is asked. Asking for 20 makes the list
# end early (87 items instead of 98 on a place where 100 gives 98), so ask for 100.
PAGE_SIZE = 100
PAUSE_SECONDS = 1.0
# Which media kinds to return; copied unchanged from the request the Maps page sends.
MEDIA_FILTERS = [[[1, 0, 3], [2, 1, 2], [2, 0, 3], [8, 0, 3], [10, 0, 3], [10, 1, 2], [10, 0, 4], [9, 1, 2]], 1]


class MapsError(RuntimeError):
    pass


def _request_body(fid, mid, page_token):
    place = [fid, None, None, None, None, None, None, None, 0, None, None, None, None, None,
             [[None, None, None, mid]] if mid else None]
    options = [None, [203, 100], [None, PAGE_SIZE, page_token, None, 1], None, None, None, MEDIA_FILTERS,
               None, 0, None, None, None, None, None, [[[[[[2]]], [195, 195], 20]]]]
    args = [2, None, place, None, options, None, None, None, None, None, None, None, None, None, None,
            [None, 1, None, 1]]
    envelope = [[["hspqX", json.dumps(args, separators=(",", ":")), None, "generic"]]]
    return urllib.parse.urlencode({"f.req": json.dumps(envelope, separators=(",", ":"))})


def _payload(response):
    """Unwrap a batchexecute response into the gallery data: [items, total, ..., next page token at 5, ...]."""
    if response["status"] != 200 or "/sorry/" in response["url"]:
        raise MapsError(f"Google refused the request (HTTP {response['status']}, {response['url'][:80]})")
    for line in response["text"].splitlines():
        if line.startswith('[["wrb.fr"'):
            inner = json.loads(line)[0][2]
            if inner:
                return json.loads(inner)
    raise MapsError("No gallery data in the response: " + response["text"][:200])


def _in_english(url):
    """Force hl=en so the address comes back in the form places.json uses."""
    parts = urllib.parse.urlsplit(url)
    query = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query) if k != "hl"] + [("hl", "en")]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))


def _attribute(tag, name):
    match = re.search(rf'\b{name}="([^"]*)"', tag)
    return html.unescape(match.group(1)) if match else None


class MapsSession:
    """An HTTP session with Google Maps that keeps cookies between requests."""

    def __enter__(self):
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self._opener.addheaders = [("User-Agent", USER_AGENT), ("Accept-Language", "en-US,en;q=0.9")]
        page, landed_on = self._get(GOOGLE + "/maps?hl=en")
        if "consent.google.com" in landed_on:
            self._reject_cookies(page)
        return self

    def __exit__(self, *exc):
        self._opener.close()

    def _open(self, request):
        """Send a request, retrying when the network fails; return (status, final url, text)."""
        for attempt in range(1, ATTEMPTS + 1):
            try:
                with self._opener.open(request, timeout=TIMEOUT) as response:
                    return response.status, response.url, response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError:      # an answer from Google, not a network failure
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt == ATTEMPTS:
                    raise
                time.sleep(2 * attempt)

    def _get(self, url):
        _, landed_on, text = self._open(url)
        return text, landed_on

    def _post(self, url, body):
        request = urllib.request.Request(url, data=body.encode(), headers={
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8"})
        status, landed_on, text = self._open(request)
        return {"status": status, "url": landed_on, "text": text}

    def _reject_cookies(self, consent_page):
        """Submit the "Reject all" form of Google's cookie-consent page."""
        for action, inner in re.findall(r'<form[^>]*\saction="([^"]+)"[^>]*>(.*?)</form>', consent_page, re.S):
            fields = {_attribute(tag, "name"): _attribute(tag, "value") or ""
                      for tag in re.findall(r"<input[^>]*>", inner) if _attribute(tag, "name")}
            if fields.get("set_eom") == "true":         # this hidden field marks the "Reject all" form
                self._post(html.unescape(action), urllib.parse.urlencode(fields))
                return
        raise MapsError('No "Reject all" form on the Google consent page')

    def open_place(self, maps_url):
        """Return the (name, address) Google shows for the place behind a Maps link."""
        page, _ = self._get(_in_english(maps_url))
        # The page's own HTML only says "Google Maps"; it names a second address to load the place card from.
        link = re.search(r'href="(/maps/preview/place[^"]+)"', page)
        if not link:
            raise MapsError(f"No place card link on the page of {maps_url}")
        text, _ = self._get(GOOGLE + html.unescape(link.group(1)))
        card = json.loads(text.split("\n", 1)[1])[6]    # the first line is the anti-JSON-hijacking prefix )]}'
        return card[11], card[39]

    def fetch_gallery_page(self, fid, mid, page_token=None):
        """Send one gallery request; return (request body as sent, response as {status, url, text})."""
        body = _request_body(fid, mid, page_token)
        return body, self._post(GOOGLE + RPC_URL, body)

    def list_gallery(self, fid, mid):
        """Return (items, total): every gallery item Google lists for the place and the count it claims.

        Items are raw nested lists, see parse.py.
        """
        items, seen, page_token = [], set(), None
        while True:
            data = _payload(self.fetch_gallery_page(fid, mid, page_token)[1])
            fresh = [item for item in (data[0] or []) if item[0] not in seen]
            seen.update(item[0] for item in fresh)
            items.extend(fresh)
            page_token = data[5]
            if not fresh or not page_token:
                total = data[1] or 0
                # A session Google does not accept gets the Street View item only (item[1] == 0),
                # while the claimed total stays the real one.
                if total > len(items) and all(item[1] == 0 for item in items):
                    raise MapsError(f"Google claims {total} gallery items but returned no photos: "
                                    "it did not accept this session. Run again in a few minutes.")
                return items, total
            time.sleep(PAUSE_SECONDS)
