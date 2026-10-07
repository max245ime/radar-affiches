"""Connecteur UGC (cinémas du réseau UGC / C2L).

Source : appel interne utilisé par la page cinéma d'ugc.fr, sans cookie ni clé :
  GET /showingsCinemaAjaxAction!getShowingsForCinemaPage.action?cinemaId=54&date=YYYY-MM-DD
Pour une date donnée, la réponse contient TOUS les films du cinéma :
  - ceux qui ont des séances ce jour-là (boutons data-showing=...)
  - les autres, avec la mention « Prochaine séance le ... »
Identifiant de film stable : filmId (ex. 18235).
"""
from __future__ import annotations
import html, re, time, urllib.request, urllib.error
from dataclasses import dataclass, field
from datetime import date

BASE = "https://www.ugc.fr"
ENDPOINT = BASE + "/showingsCinemaAjaxAction!getShowingsForCinemaPage.action"
USER_AGENT = "RadarAffiches/0.1 (usage personnel, faible frequence)"

MOIS = {"janv.": 1, "févr.": 2, "mars": 3, "avr.": 4, "mai": 5, "juin": 6, "juil.": 7,
        "août": 8, "sept.": 9, "oct.": 10, "nov.": 11, "déc.": 12}


class FetchError(Exception):
    """Récupération impossible ou réponse inexploitable (=> ne JAMAIS en déduire des déprogrammations)."""


@dataclass
class Film:
    film_id: str
    title: str
    url: str = ""
    tag: str = ""                 # ex. « Sélection UGC Family », avant-première...
    is_new: bool = False          # mention « Nouveau »
    next_showing: date | None = None  # « Prochaine séance le ... » (si pas de séance ce jour)
    poster: str = ""


@dataclass
class Showing:
    showing_id: str
    film_id: str
    day: date
    start: str                    # "13:15"
    end: str = ""                 # "15:17"
    version: str = ""             # VF / VOSTF ...
    room: str = ""


@dataclass
class DayResult:
    cinema_id: int
    day: date
    films: dict[str, Film] = field(default_factory=dict)   # tous les films du cinéma
    showings: list[Showing] = field(default_factory=list)


def fetch_day_html(cinema_id: int, day: date, timeout: int = 20, retries: int = 2) -> str:
    url = f"{ENDPOINT}?cinemaId={cinema_id}&date={day.isoformat()}&page=30007&searchFilmKey="
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "text/html, */*; q=0.01",
        "Accept-Language": "fr-FR,fr;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{BASE}/cinema.html?id={cinema_id}",
    })
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise FetchError(f"Échec de récupération {day}: {last}")


def _txt(s: str) -> str:
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def _parse_fr_date(text: str) -> date | None:
    """« Prochaine séance le jeudi 8 oct. 2026 » -> date(2026,10,8)."""
    m = re.search(r"Prochaine séance le \w+ (\d{1,2}) (\S+) (\d{4})", text)
    if not m:
        return None
    mois = MOIS.get(m.group(2))
    return date(int(m.group(3)), mois, int(m.group(1))) if mois else None


def parse_cinema_page(page: str, cinema_id: int, day: date) -> DayResult:
    res = DayResult(cinema_id=cinema_id, day=day)
    script_free = re.sub(r"<script.*?</script>", "", page, flags=re.S)
    blocks = re.split(r'(?=<div id="bloc-showing-film-\d+")', script_free)[1:]
    for b in blocks:
        fid = re.match(r'<div id="bloc-showing-film-(\d+)"', b).group(1)
        t = re.search(r'<a id="goToFilm_\d+_info_title"[^>]*?title="([^"]+)"', b) \
            or re.search(r'title="([^"]+)"', b)
        title = html.unescape(t.group(1)).strip() if t else f"film {fid}"
        u = re.search(r'href="(https://www\.ugc\.fr/film_[^"?]+\.html)', b)
        tag = re.search(r'class="film-tag[^>]*>\s*([^<]+?)\s*<', b)
        newf = re.search(r'nb-week[^>]*>\s*Nouveau', b) is not None
        res.films[fid] = Film(
            film_id=fid, title=title, url=u.group(1) if u else "",
            tag=html.unescape(tag.group(1)).strip() if tag else "", is_new=newf,
            next_showing=_parse_fr_date(_txt(b)),
            poster=(re.search(r'data-src="(https://www\.ugc\.fr/dynamique/films/[^"]+)"', b) or [None, ""])[1],
        )
        for btn in re.finditer(r'<button\b[^>]*data-showing="(\d+)"[^>]*>(.*?)</button>', b, flags=re.S):
            attrs = dict(re.findall(r'data-(\w+)="([^"]*)"', btn.group(0).split(">", 1)[0]))
            body = btn.group(2)
            d, mth, y = attrs["seanceDate"].split("/")
            end = re.search(r"fin (\d{2}:\d{2})", body)
            room = re.search(r"(Salle\s*\S+)", _txt(body))
            res.showings.append(Showing(
                showing_id=btn.group(1), film_id=attrs.get("filmId", fid), day=date(int(y), int(mth), int(d)),
                start=attrs["seanceHour"], end=end.group(1) if end else "",
                version=attrs.get("version", ""), room=room.group(1) if room else ""))
    if not res.films:
        raise FetchError(f"Aucun film trouvé pour {day} : format de page changé ou réponse invalide.")
    return res


def fetch_day(cinema_id: int, day: date) -> DayResult:
    return parse_cinema_page(fetch_day_html(cinema_id, day), cinema_id, day)
