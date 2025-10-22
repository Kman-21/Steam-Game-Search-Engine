from flask import Flask, render_template, request, redirect, url_for
import requests, os, json, time, datetime

app = Flask(__name__)

STEAM_APP_LIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

# paths for cached data
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APPS_CACHE = os.path.join(BASE_DIR, "apps_cache.json")
HISTORY_FILE = os.path.join(BASE_DIR, "search_history.json")

def load_apps_cache():
    if os.path.exists(APPS_CACHE):
        try:
            with open(APPS_CACHE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_apps_cache(data):
    with open(APPS_CACHE, "w", encoding="utf-8") as f:
        json.dump(data, f)

def fetch_and_cache_apps():
    # fetch app list from Steam and cache it (this may take a few seconds)
    r = requests.get(STEAM_APP_LIST_URL, timeout=30)
    r.raise_for_status()
    data = r.json().get("applist", {}).get("apps", [])
    save_apps_cache(data)
    return data

def get_all_apps():
    apps = load_apps_cache()
    if apps is None:
        apps = fetch_and_cache_apps()
    return apps

def search_apps(query, limit=10):
    q = query.lower()
    apps = get_all_apps()
    matches = []
    for app in apps:
        name = app.get("name","")
        if q in name.lower():
            matches.append(app)
            if len(matches) >= limit:
                break
    return matches

def get_app_details(appid):
    params = {"appids": appid, "cc": "us", "l": "en"}
    r = requests.get(STEAM_APP_DETAILS_URL, params=params, timeout=15)
    if r.status_code != 200:
        return None
    data = r.json().get(str(appid), {})
    if not data.get("success"):
        return None
    info = data.get("data", {})
    result = {
        "appid": appid,
        "name": info.get("name", "Unknown"),
        "description": info.get("short_description", "No description available."),
        "is_free": info.get("is_free", False),
        "price": info.get("price_overview", {}).get("final_formatted") if info.get("price_overview") else ("Free" if info.get("is_free") else "N/A"),
        "rating": info.get("metacritic", {}).get("score", "N/A"),
        "header_image": info.get("header_image") or info.get("screenshots", [{}])[0].get("path_full") or "",
        "steam_url": f"https://store.steampowered.com/app/{appid}"
    }
    return result

def append_history(entry):
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = []
    history.insert(0, entry)  # newest first
    # keep last 100 entries
    history = history[:100]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    results = None
    query = ""
    if request.method == "POST":
        query = request.form.get("game_name","").strip()
        if query:
            try:
                results = search_apps(query, limit=15)
                # save search query to history (no selection yet)
                append_history({
                    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                    "type": "search",
                    "query": query,
                    "result_count": len(results)
                })
            except Exception as e:
                error = str(e)
        else:
            error = "Please enter a game name."
    history = load_history()[:20]
    return render_template("index.html", results=results, query=query, error=error, history=history)

@app.route("/select/<int:appid>", methods=["GET"])
def select(appid):
    details = get_app_details(appid)
    if details is None:
        return "Could not fetch details for that app.", 500
    # save selection to history
    append_history({
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "type": "select",
        "appid": appid,
        "name": details.get("name"),
    })
    return render_template("details.html", details=details)

@app.route("/history", methods=["GET"])
def history():
    history = load_history()[:100]
    return render_template("history.html", history=history)

@app.route("/refresh_apps_cache", methods=["GET"])
def refresh_cache():
    try:
        fetch_and_cache_apps()
        return "Apps cache refreshed.", 200
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    from waitress import serve
    serve(app, host="0.0.0.0", port=10000)

