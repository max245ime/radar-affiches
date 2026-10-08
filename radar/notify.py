"""Notifications : push intégré à l'app (serveur Cloudflare) et/ou ntfy. Les deux sont optionnels."""
import json, os, urllib.request

UA = "RadarAffiches/0.2 (usage personnel)"


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json", "User-Agent": UA, **headers})
    urllib.request.urlopen(req, timeout=25).read()


def send(title: str, message: str, priority: int = 3, tags=None, click: str = "") -> bool:
    ok, configured = False, False
    push_url, push_secret = os.environ.get("PUSH_URL", "").strip().rstrip("/"), os.environ.get("PUSH_SECRET", "").strip()
    if push_url and push_secret:
        configured = True
        try:
            _post(push_url + "/notify", {"title": title, "message": message, "click": click}, {"Authorization": f"Bearer {push_secret}"})
            ok = True
        except Exception as e:
            print("push intégré: échec d'envoi:", e)
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if topic:
        configured = True
        body = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": tags or []}
        if click:
            body["click"] = click
        try:
            _post(os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/"), body, {})
            ok = True
        except Exception as e:
            print("ntfy: échec d'envoi:", e)
    if not configured:
        print(f"[aucune notification configurée] {title}\n{message}")
    return ok
