import requests
import json
import os
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from google_play_scraper import app as gplay_app

RATINGS_FILE = "ratings.json"


def load_existing():
    if os.path.exists(RATINGS_FILE):
        with open(RATINGS_FILE) as f:
            return json.load(f)
    return {"last_updated": None, "history": []}


def save(data):
    with open(RATINGS_FILE, "w") as f:
        json.dump(data, f, indent=2)


def fetch_apple():
    try:
        resp = requests.get(
            "https://itunes.apple.com/search",
            params={
                "term": "betterhelp",
                "entity": "software",
                "country": "us",
                "limit": 10,
            },
            timeout=15,
        )
        resp.raise_for_status()
        for result in resp.json().get("results", []):
            bundle = result.get("bundleId", "").lower()
            name = result.get("trackName", "").lower()
            if "betterhelp" in bundle or name == "betterhelp - therapy":
                return {
                    "rating": round(result.get("averageUserRating", 0), 2),
                    "count": result.get("userRatingCount", 0),
                }
    except Exception as e:
        print(f"Apple fetch error: {e}")
    return None


def fetch_google():
    try:
        result = gplay_app("com.betterhelp", lang="en", country="us")
        return {
            "rating": round(result.get("score", 0), 2),
            "count": result.get("ratings", 0),
        }
    except Exception as e:
        print(f"Google fetch error: {e}")
    return None


def fetch_trustpilot():
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(
            "https://www.trustpilot.com/review/www.betterhelp.com",
            headers=headers,
            timeout=20,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Primary: Next.js hydration data (most reliable)
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data:
            try:
                data = json.loads(next_data.string or "")
                props = data.get("props", {}).get("pageProps", {})
                # businessUnit is nested in different paths depending on page version
                for key in ("businessUnit", "business"):
                    bu = props.get(key, {})
                    if bu.get("trustScore"):
                        return {
                            "rating": round(float(bu["trustScore"]), 2),
                            "count": int(bu.get("numberOfReviews", {}).get("total", 0)),
                        }
            except Exception:
                pass

        # Fallback: JSON-LD structured data
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
                items = data if isinstance(data, list) else [data]
                for item in items:
                    ar = item.get("aggregateRating")
                    if ar:
                        return {
                            "rating": round(float(ar.get("ratingValue", 0)), 2),
                            "count": int(ar.get("reviewCount", 0)),
                        }
            except Exception:
                pass

    except Exception as e:
        print(f"TrustPilot fetch error: {e}")
    return None


def main():
    print("Fetching ratings...")
    apple = fetch_apple()
    google = fetch_google()
    trustpilot = fetch_trustpilot()

    print(f"  Apple App Store : {apple}")
    print(f"  Google Play     : {google}")
    print(f"  TrustPilot      : {trustpilot}")

    if not any([apple, google, trustpilot]):
        print("All fetches failed — skipping update.")
        return

    data = load_existing()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    entry = {"date": today}
    if apple:
        entry["apple"] = apple
    if google:
        entry["google"] = google
    if trustpilot:
        entry["trustpilot"] = trustpilot

    history = [e for e in data.get("history", []) if e["date"] != today]
    history.append(entry)
    history.sort(key=lambda x: x["date"])

    data["last_updated"] = datetime.now(timezone.utc).isoformat()
    data["history"] = history

    save(data)
    print(f"Saved ratings for {today}.")


if __name__ == "__main__":
    main()
