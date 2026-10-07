"""Tâche automatique : relève UGC, met à jour l'historique, détecte, notifie, écrit docs/data.json."""
from __future__ import annotations
import json, os, sys, time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from . import notify
from .compare import compare, summarize, week_start
from .ugc import DayResult, Film, FetchError, Showing, fetch_day

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
OUT = ROOT / "docs" / "data.json"
DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
CINEMA_FETCH = fetch_day  # remplaçable dans les tests


def load_state():
    return json.loads(STATE.read_text("utf-8")) if STATE.exists() else {"cinemas": {}}


def next_pickup(slots, today: date):
    best = None
    for s in slots:
        wd = DAYS_EN.index(s["day"].lower())
        d = today + timedelta(days=(wd - today.weekday()) % 7)
        if best is None or d < best[0]:
            best = (d, s)
    return {"date": best[0].isoformat(), "day": DAYS_FR[best[0].weekday()], "start": best[1]["start"],
            "end": best[1]["end"], "is_today": best[0] == today} if best else None


def slot_text(slots):
    return " / ".join(f"{DAYS_FR[DAYS_EN.index(s['day'].lower())]} {s['start'].replace(':00','h')}–{s['end'].replace(':00','h')}" for s in slots)


def refresh(cin, cs, today: date, delay: float):
    w0 = week_start(today)
    fetched = set(cs.setdefault("fetched", []))
    for i in range(14):
        d = w0 + timedelta(days=i)
        if d < today and d.isoformat() in fetched:
            continue
        r: DayResult = CINEMA_FETCH(cin["id"], d)
        for fid, f in r.films.items():
            cs.setdefault("films", {})[fid] = {"title": f.title, "url": f.url, "poster": f.poster, "tag": f.tag,
                "next": f.next_showing.isoformat() if f.next_showing else None, "seen": today.isoformat()}
        seen = {s.showing_id for s in r.showings}
        sess = cs.setdefault("sessions", {})
        if d > today:  # jours futurs : la liste du site fait foi (séance annulée = retirée)
            for sid in [k for k, v in sess.items() if v["d"] == d.isoformat() and k not in seen]:
                del sess[sid]
        for s in r.showings:
            sess[s.showing_id] = {"f": s.film_id, "d": s.day.isoformat(), "t": s.start, "e": s.end, "v": s.version, "r": s.room}
        fetched.add(d.isoformat())
        time.sleep(delay)
    cs["fetched"] = sorted(fetched)
    cutoff = (today - timedelta(days=120)).isoformat()
    cs["sessions"] = {k: v for k, v in cs["sessions"].items() if v["d"] >= cutoff}
    cs["fetched"] = [d for d in cs["fetched"] if d >= cutoff]


def rebuild(cs, cin_id) -> list[DayResult]:
    by: dict[str, DayResult] = {d: DayResult(cin_id, date.fromisoformat(d)) for d in cs["fetched"]}
    for sid, v in cs["sessions"].items():
        if v["d"] in by:
            by[v["d"]].showings.append(Showing(sid, v["f"], date.fromisoformat(v["d"]), v["t"], v["e"], v["v"], v["r"]))
    return list(by.values())


def films_obj(cs):
    return {k: Film(k, v["title"], v.get("url", ""), v.get("tag", ""), False,
                    date.fromisoformat(v["next"]) if v.get("next") else None, v.get("poster", "")) for k, v in cs.get("films", {}).items()}


def process(cin, cs, today: date, now: datetime, app_url: str):
    w0 = week_start(today); w1 = w0 + timedelta(days=7)
    days = rebuild(cs, cin["id"])
    cur, nxt = summarize(days, w0), summarize(days, w1)
    films = films_obj(cs)
    dets = cs.setdefault("detections", {})
    notified = set(cs.setdefault("notified", []))
    if nxt.published and cur.complete and nxt.complete:
        found = {(d.film.film_id): d for d in compare(cur, nxt, films) if d.kind == "removed"}
        for fid, d in found.items():
            key = f"{w1.isoformat()}:{fid}"
            if key not in dets:
                dets[key] = {"film_id": fid, "title": d.film.title, "url": d.film.url, "poster": d.film.poster,
                             "status": d.status, "reason": d.reason, "sessions_prev": d.sessions_prev,
                             "last": f"{d.last_showing[0].isoformat()} {d.last_showing[1]}" if d.last_showing else "",
                             "leaves": w1.isoformat(), "detected": now.isoformat(timespec="minutes")}
        for key in [k for k, v in dets.items() if v["leaves"] == w1.isoformat() and v["film_id"] not in found]:
            del dets[key]  # le film est finalement reprogrammé
    for k in [k for k, v in dets.items() if date.fromisoformat(v["leaves"]) + timedelta(days=7) <= today]:
        del dets[k]
    slots = cin["pickup"]; txt = slot_text(slots)
    # 1) alerte dès la détection
    fresh = [v for k, v in dets.items() if k not in notified]
    if fresh:
        probable = [v for v in fresh if v["status"] == "🟠"]; verif = [v for v in fresh if v["status"] != "🟠"]
        lines = []
        for v in probable:
            ls = ""
            if v["last"]:
                dd = date.fromisoformat(v["last"][:10]); ls = f" (dernière séance {DAYS_FR[dd.weekday()]} {v['last'][11:]})"
            lines.append(f"• {v['title']}{ls}")
        if verif:
            lines.append("À vérifier : " + ", ".join(v["title"] for v in verif))
        msg = (f"Ne sont plus au programme à partir de {DAYS_FR[w1.weekday()]} {w1:%d/%m} :\n" + "\n".join(lines) +
               f"\n\nÀ récupérer : {txt}.\nDétection automatique, à confirmer sur place.")
        if probable:
            notify.send(f"🎬 {len(probable)} affiche(s) à récupérer – {cin['name']}", msg, 4, ["clapper"], app_url)
        for k in [k for k, v in dets.items() if k not in notified]:
            notified.add(k)
    # 2) rappel le jour du créneau, si des films partent ensuite
    np = next_pickup(slots, today)
    rk = f"reminder:{today.isoformat()}"
    todo = [v for v in dets.values() if v["status"] == "🟠" and date.fromisoformat(v["leaves"]) > today]
    if np and np["is_today"] and todo and rk not in notified and now.hour >= 8:
        notify.send(f"🚨 Affiches à récupérer aujourd'hui – {cin['name']}",
                    "\n".join(f"• {v['title']}" for v in todo) + f"\n\nCréneau : {np['start']}–{np['end']}.", 5, ["rotating_light"], app_url)
        notified.add(rk)
    cs["notified"] = sorted(notified)[-300:]
    wk = [{"film_id": f, "title": films[f].title if f in films else f, "sessions": n,
           "poster": films[f].poster if f in films else "", "url": films[f].url if f in films else ""}
          for f, n in sorted(cur.sessions.items(), key=lambda x: -x[1])]
    return {"id": cin["id"], "name": cin["name"], "slots": slots, "pickup_text": txt, "next_pickup": np,
            "week_start": w0.isoformat(), "next_week_published": nxt.published,
            "films_now": wk, "films_total": len(films), "detections": sorted(dets.values(), key=lambda v: (v["status"] != "🟠", v["title"]))}


def main():
    cfg = json.loads((ROOT / "config.json").read_text("utf-8"))
    tz = ZoneInfo(cfg.get("timezone", "Europe/Paris")); now = datetime.now(tz); today = now.date()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    app_url = f"https://{repo.split('/')[0]}.github.io/{repo.split('/')[1]}/" if "/" in repo else ""
    state = load_state(); out = json.loads(OUT.read_text("utf-8")) if OUT.exists() else {"cinemas": []}
    results, errors = {c["id"]: c for c in out.get("cinemas", [])}, []
    for cin in cfg["cinemas"]:
        cs = state["cinemas"].setdefault(str(cin["id"]), {})
        try:
            refresh(cin, cs, today, cfg.get("request_delay_seconds", 2))
            cs["last_ok"] = now.isoformat(timespec="minutes")
            results[cin["id"]] = process(cin, cs, today, now, app_url)
        except FetchError as e:
            errors.append(f"{cin['name']}: {e}")
            print("ERREUR (aucune déprogrammation déduite):", e, file=sys.stderr)
            lo = cs.get("last_ok")
            if lo and now - datetime.fromisoformat(lo) > timedelta(hours=24) and cs.get("err_notif") != today.isoformat():
                notify.send("⚠️ Radar Affiches : relevé en échec", f"Plus de relevé réussi pour {cin['name']} depuis 24 h.", 2, ["warning"], app_url)
                cs["err_notif"] = today.isoformat()
    for c in results.values():
        c["last_ok"] = state["cinemas"].get(str(c["id"]), {}).get("last_ok")
    OUT.parent.mkdir(exist_ok=True); STATE.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"updated": now.isoformat(timespec="minutes"), "status": "error" if errors else "ok",
                               "errors": errors, "cinemas": list(results.values())}, ensure_ascii=False, indent=1), "utf-8")
    STATE.write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), "utf-8")
    print("OK" if not errors else "terminé avec erreurs")


if __name__ == "__main__":
    main()
