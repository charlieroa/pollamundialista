# -*- coding: utf-8 -*-
"""Baja los resultados REALES del Mundial 2026 desde TheSportsDB (gratis).

El plan Free de API-Football no da acceso a la temporada 2026, asi que los
resultados en vivo se toman de TheSportsDB (liga 4429, temporada 2026, key
publica). Escribe results.json indexado por par de equipos (sin orden), que
luego leen predict.py y bracket.py para colorear aciertos y marcar "hoy".

Tolerante a fallos: si la API falla, conserva el results.json previo.
"""
import json
import sys
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent / "results.json"
URL = "https://www.thesportsdb.com/api/v1/json/123/eventsseason.php?id=4429&s=2026"

# Nombres de TheSportsDB -> nombres internos del modelo (predict.py)
ALIASES = {
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Czechia": "Czech Republic",
    "Czech Republic": "Czech Republic",
    "Korea Republic": "South Korea",
    "South Korea": "South Korea",
    "Korea DPR": "North Korea",
    "United States": "USA",
    "USA": "USA",
    "Turkiye": "Turkey",
    "Türkiye": "Turkey",
    "Turkey": "Turkey",
    "Ivory Coast": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "DR Congo": "Congo DR",
    "Congo DR": "Congo DR",
    "Cape Verde": "Cape Verde",
    "Cabo Verde": "Cape Verde",
    "Saudi Arabia": "Saudi Arabia",
    "Curacao": "Curacao",
    "Curaçao": "Curacao",
}


def norm(name):
    return ALIASES.get(name.strip(), name.strip())


def pair_key(a, b):
    """Clave estable independiente del orden local/visitante."""
    return "||".join(sorted([a, b]))


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def main():
    try:
        data = fetch()
    except Exception as e:
        if OUT.exists():
            print(f"AVISO: fallo la API ({e}); conservo results.json previo.")
            return
        print(f"ERROR: fallo la API y no hay results.json previo: {e}")
        sys.exit(1)

    events = data.get("events") or []
    results = {}
    played = 0
    for ev in events:
        home = norm(ev.get("strHomeTeam", ""))
        away = norm(ev.get("strAwayTeam", ""))
        gh, ga = ev.get("intHomeScore"), ev.get("intAwayScore")
        status = (ev.get("strStatus") or "").strip()
        date = ev.get("dateEvent") or ""
        finished = status in ("FT", "AET", "PEN", "Match Finished") and gh is not None and ga is not None
        entry = {
            "home": home, "away": away,
            "gh": int(gh) if finished else None,
            "ga": int(ga) if finished else None,
            "status": "FT" if finished else (status or "NS"),
            "date": date,
        }
        results[pair_key(home, away)] = entry
        if finished:
            played += 1

    payload = {"source": "thesportsdb", "league": 4429, "season": 2026,
               "count": len(results), "played": played, "matches": results}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK -> {OUT}  ({len(results)} partidos, {played} jugados)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
