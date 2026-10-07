from datetime import date, timedelta
from radar.ugc import DayResult, Film, Showing
from radar.compare import week_start, summarize, compare

def mk(day, spec):  # spec: {film_id: nb_seances}
    r = DayResult(54, day)
    for fid, n in spec.items():
        for i in range(n):
            r.showings.append(Showing(f"{fid}{day}{i}", fid, day, f"{14+i}:00"))
    return r

def test_week_start():
    assert week_start(date(2026, 10, 7)) == date(2026, 10, 7)   # mercredi
    assert week_start(date(2026, 10, 13)) == date(2026, 10, 7)  # mardi
    assert week_start(date(2026, 10, 14)) == date(2026, 10, 14)

def test_detection():
    w0 = date(2026, 10, 7)
    films = {"A": Film("A", "Film A"), "B": Film("B", "Film B"), "C": Film("C", "Film C"),
             "D": Film("D", "Film D"), "E": Film("E", "Film E", next_showing=date(2026, 12, 1))}
    days = [mk(w0 + timedelta(i), {"A": 2, "B": 2, "C": 1, "E": 1}) for i in range(7)] + \
           [mk(w0 + timedelta(7 + i), {"A": 2, "C": 1, "D": 2}) for i in range(7)]
    d = compare(summarize(days, w0), summarize(days, w0 + timedelta(7)), films)
    by = {(x.kind, x.film.film_id): x.status for x in d}
    assert by[("removed", "B")] == "🟠"
    assert by[("removed", "E")] == "⚪"       # revient en décembre
    assert by[("new", "D")] == "🆕"
    assert ("removed", "A") not in by and ("removed", "C") not in by

def test_next_week_not_published_gives_nothing():
    w0 = date(2026, 10, 7)
    days = [mk(w0 + timedelta(i), {"A": 2}) for i in range(7)] + \
           [mk(w0 + timedelta(7 + i), {} if i == 0 else {"X": 1}) for i in range(7)]
    assert compare(summarize(days, w0), summarize(days, w0 + timedelta(7)), {}) == []

def test_incomplete_refused():
    w0 = date(2026, 10, 7)
    days = [mk(w0 + timedelta(i), {"A": 1}) for i in range(10)]
    try:
        compare(summarize(days, w0), summarize(days, w0 + timedelta(7)), {})
        assert False
    except ValueError:
        pass
