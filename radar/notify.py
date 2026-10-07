"""Notifications push via ntfy (https://ntfy.sh) : app Android gratuite, aucun compte requis."""
import json, os, urllib.request

def send(title: str, message: str, priority: int = 3, tags=None, click: str = "") -> bool:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print(f"[ntfy désactivé : NTFY_TOPIC absent] {title}\n{message}")
        return False
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    body = {"topic": topic, "title": title, "message": message, "priority": priority, "tags": tags or []}
    if click:
        body["click"] = click
    req = urllib.request.Request(server, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20).read()
        return True
    except Exception as e:  # une notif ratée ne doit pas casser le relevé
        print("ntfy: échec d'envoi:", e)
        return False
