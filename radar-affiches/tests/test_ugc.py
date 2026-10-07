from datetime import date
from pathlib import Path
from radar.ugc import parse_cinema_page

PAGE = (Path(__file__).parent / "fixtures" / "ugc54_2026-10-10.html").read_text(encoding="utf-8")

def test_real_page():
    r = parse_cinema_page(PAGE, 54, date(2026, 10, 10))
    assert len(r.films) == 28                      # « 28 films » annoncés par UGC pour Poissy
    assert len(r.showings) == 19
    assert r.films["18235"].title == "HEART OF THE BEAST"
    assert r.films["17771"].next_showing == date(2026, 10, 8)
    assert r.films["9004"].next_showing == date(2026, 10, 11)
    assert r.films["17493"].is_new
    s = [x for x in r.showings if x.film_id == "17493"][0]
    assert (s.start, s.version) == ("13:40", "VF") and s.end and s.room
    assert all(x.day == date(2026, 10, 10) for x in r.showings)

def test_invalid_page_raises():
    import pytest
    from radar.ugc import FetchError
    with pytest.raises(FetchError):
        parse_cinema_page("<html>maintenance</html>", 54, date(2026, 10, 10))
