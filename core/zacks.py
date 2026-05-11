import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.zacks.com/",
}

_LOGIN_POST = "https://www.zacks.com/user/login.php"
_QUOTE_URL  = "https://www.zacks.com/stock/quote/{ticker}"


class ZacksClient:
    def __init__(self):
        self.session = requests.Session()
        self.logged_in = False

    def login(self, username: str, password: str, debug: bool = False) -> bool:
        login_page = self.session.get("https://www.zacks.com/login.php", headers=_HEADERS)
        soup = BeautifulSoup(login_page.text, "html.parser")

        # Find the login form and its action URL
        form = soup.find("form", {"id": "login_form"}) or soup.find("form")
        if form:
            action = form.get("action", "").strip()
            if action.startswith("/"):
                action = "https://www.zacks.com" + action
            elif not action.startswith("http"):
                action = "https://www.zacks.com/" + action
        else:
            action = _LOGIN_POST

        # Collect hidden fields from the form
        payload = {}
        if form:
            for inp in form.find_all("input", {"type": "hidden"}):
                name = inp.get("name")
                value = inp.get("value", "")
                if name:
                    payload[name] = value

        payload.update({
            "username":    username,
            "password":    password,
            "remember_me": "on",
        })

        if debug:
            print(f"[zacks login] form action: {action}")
            print(f"[zacks login] payload keys: {list(payload.keys())}")

        post_headers = {**_HEADERS, "Referer": "https://www.zacks.com/login.php"}
        resp = self.session.post(action, data=payload, headers=post_headers, allow_redirects=True)

        if debug:
            print(f"[zacks login] status: {resp.status_code}")
            print(f"[zacks login] final url: {resp.url}")
            print(f"[zacks login] cookies: {dict(self.session.cookies)}")
            print(f"[zacks login] response body (first 500 chars):\n{resp.text[:500]}")

        fail_phrases = ["invalid password", "incorrect", "login failed", "error logging in"]
        if any(p in resp.text.lower() for p in fail_phrases):
            self.logged_in = False
            return False
        self.logged_in = resp.status_code == 200
        return self.logged_in

    def get_quote_data(self, ticker: str, debug: bool = False) -> dict:
        """Return {"vgm": str, "rank": str} fetched in a single request."""
        url = _QUOTE_URL.format(ticker=ticker.upper())
        resp = self.session.get(url, headers=_HEADERS)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # VGM score
        vgm = "N/A"
        for span in soup.find_all("span", class_="composite_val_vgm"):
            if span.find_parent(class_="tooltiptext"):
                continue
            v = span.get_text(strip=True)
            if v:
                vgm = v
                break

        # Zacks Rank — try known selectors
        rank = "N/A"
        rank_tag = soup.find("p", class_="rank_view")
        if rank_tag:
            rank = rank_tag.get_text(strip=True)
        if rank == "N/A":
            for tag in soup.find_all(class_=lambda c: c and "zr_rankbox" in c):
                if tag.find_parent(class_="tooltiptext"):
                    continue
                t = tag.get_text(strip=True)
                if t:
                    rank = t
                    break

        first_digit = next((c for c in rank if c.isdigit()), None)
        rank = first_digit if first_digit else "N/A"

        if debug:
            print(f"[zacks {ticker}] vgm={vgm!r}  rank={rank!r}")

        return {"vgm": vgm, "rank": rank}

    def get_vgm(self, ticker: str) -> str:
        return self.get_quote_data(ticker)["vgm"]
