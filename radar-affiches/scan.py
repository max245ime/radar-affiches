"""Usage : python scan.py [--cinema 54] [--name "C2L Poissy"] [--today 2026-10-07] [--save]
Relève la semaine cinéma en cours + la suivante (14 requêtes max, 2 s entre chaque),
puis affiche les déprogrammations probables."""
import argparse, json, sys, time
from datetime import date, datetime, timedelta
from radar.ugc import fetch_day, FetchError
from radar.compare import week_start, summarize, compare

FR = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cinema", type=int, default=54)
    ap.add_argument("--name", default="C2L Poissy")
    ap.add_argument("--today", default=None, help="AAAA-MM-JJ (test)")
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--save", action="store_true", help="enregistre un relevé JSON dans data/")
    a = ap.parse_args()
    today = date.fromisoformat(a.today) if a.today else date.today()
    w0 = week_start(today); w1 = w0 + timedelta(days=7)
    days, films = [], {}
    try:
        for i in range(14):
            d = w0 + timedelta(days=i)
            r = fetch_day(a.cinema, d)
            days.append(r); films.update(r.films)
            print(f"  relevé {d:%d/%m} : {len(r.showings):3d} séances / {len(r.films)} films", file=sys.stderr)
            if i < 13: time.sleep(a.delay)
    except FetchError as e:
        print(f"\n❌ {e}\nAucune conclusion tirée (une erreur n'est PAS une déprogrammation).")
        sys.exit(1)
    cur, nxt = summarize(days, w0), summarize(days, w1)
    def show(title, wk):
        print(f"\n{title} ({wk.start:%d/%m} → {wk.start + timedelta(days=6):%d/%m}) :")
        for fid, n in sorted(wk.sessions.items(), key=lambda x: -x[1]):
            print(f"- {films[fid].title} — {n} séances")
    print(f"\n{a.name}")
    show("Semaine actuelle", cur)
    if not nxt.published:
        print(f"\nSemaine suivante : pas encore publiée par UGC (aucune séance le {w1:%d/%m}). Détection impossible pour l'instant.")
        dets = []
    else:
        show("Semaine suivante", nxt)
        dets = compare(cur, nxt, films)
        print("\nDétection :")
        if not dets: print("(rien)")
        for x in dets:
            ls = f" — dernière séance {FR[x.last_showing[0].weekday()]} {x.last_showing[0]:%d/%m} {x.last_showing[1]}" if x.last_showing else ""
            icon = {"removed": x.status, "new": "🆕"}[x.kind]
            print(f"{icon} {x.film.title}{ls}\n     {x.reason}")
    if a.save:
        import os; os.makedirs("data", exist_ok=True)
        fn = f"data/{a.cinema}_{datetime.now():%Y%m%d_%H%M}.json"
        json.dump([{"day": d.day.isoformat(), "showings": [s.__dict__ | {"day": s.day.isoformat()} for s in d.showings],
                    "films": {k: {"title": f.title, "next": f.next_showing.isoformat() if f.next_showing else None}
                              for k, f in d.films.items()}} for d in days], open(fn, "w"), ensure_ascii=False, indent=1)
        print(f"\nRelevé enregistré : {fn}")

if __name__ == "__main__":
    main()
