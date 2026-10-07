"""Comparaison de deux semaines de programmation (semaine cinéma = mercredi -> mardi).

Niveaux de confiance (v0, sans historique en base) :
  🟠 probablement déprogrammé : séances en semaine N, aucune en N+1, rien d'annoncé plus tard.
  ⚪ à vérifier              : absent de N+1 mais UGC annonce une « prochaine séance » plus tard
                               (reprise, événement, séance spéciale) ou film à séance unique.
  🔴 forte confiance          : réservé au backend (absence confirmée sur plusieurs relevés
                               successifs) — nécessite l'historique, pas encore là.
Règle de sécurité : si la semaine N+1 n'est pas encore publiée (aucune séance le mercredi,
jour de changement de programme) ou si un relevé a échoué, AUCUNE détection n'est émise.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date, timedelta
from .ugc import DayResult, Film

WEDNESDAY = 2


def week_start(d: date) -> date:
    return d - timedelta(days=(d.weekday() - WEDNESDAY) % 7)


@dataclass
class WeekSummary:
    start: date
    sessions: dict[str, int]            # film_id -> nb de séances
    last: dict[str, tuple[date, str]]   # film_id -> dernière séance (jour, heure)
    complete: bool                      # les 7 jours ont bien été relevés
    published: bool                     # séances le mercredi => programme publié


@dataclass
class Detection:
    kind: str            # "removed" | "new"
    status: str
    film: Film
    reason: str = ""
    sessions_prev: int = 0
    last_showing: tuple[date, str] | None = None


def summarize(days: list[DayResult], start: date) -> WeekSummary:
    wk = [d for d in days if start <= d.day < start + timedelta(days=7)]
    sessions: dict[str, int] = {}
    last: dict[str, tuple[date, str]] = {}
    for d in wk:
        for s in d.showings:
            sessions[s.film_id] = sessions.get(s.film_id, 0) + 1
            if s.film_id not in last or (s.day, s.start) > last[s.film_id]:
                last[s.film_id] = (s.day, s.start)
    wed = [d for d in wk if d.day == start]
    return WeekSummary(start, sessions, last,
                       complete=len({d.day for d in wk}) == 7,
                       published=bool(wed and wed[0].showings))


def compare(cur: WeekSummary, nxt: WeekSummary, films: dict[str, Film]) -> list[Detection]:
    if not (cur.complete and nxt.complete):
        raise ValueError("Relevé incomplet : comparaison refusée (évite les faux positifs).")
    if not nxt.published:
        return []
    out: list[Detection] = []
    nxt_end = nxt.start + timedelta(days=7)
    for fid, n in cur.sessions.items():
        if fid in nxt.sessions:
            continue
        f = films.get(fid) or Film(fid, f"film {fid}")
        if f.next_showing and f.next_showing >= nxt_end:
            st, why = "⚪", f"Revient plus tard (prochaine séance le {f.next_showing:%d/%m/%Y}) : reprise/événement ?"
        elif n == 1:
            st, why = "⚪", "Séance unique la semaine passée : événement probable."
        else:
            st, why = "🟠", "Absent de la programmation de la semaine suivante."
        out.append(Detection("removed", st, f, why, n, cur.last.get(fid)))
    for fid, n in nxt.sessions.items():
        if fid not in cur.sessions:
            out.append(Detection("new", "🆕", films.get(fid) or Film(fid, f"film {fid}"), "Nouveau film", n))
    return out
