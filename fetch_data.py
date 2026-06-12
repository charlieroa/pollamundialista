# -*- coding: utf-8 -*-
"""Descarga y cachea datos de API-Football para la polla del Mundial 2026.

Plan Free: 100 req/dia, ~10 req/min, solo temporadas 2022-2024.
Cada respuesta se cachea en data/ y se reanuda sin gastar requests.
"""
import json
import os
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path


def _load_api_key():
    key = os.environ.get("API_FOOTBALL_KEY")
    if key:
        return key
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith("API_FOOTBALL_KEY="):
                return line.split("=", 1)[1].strip()
    sys.exit("Falta API_FOOTBALL_KEY (variable de entorno o archivo .env)")


API_KEY = _load_api_key()
BASE = "https://v3.football.api-sports.io"
DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)

THROTTLE_SECONDS = 7  # ~8.5 req/min, bajo el limite de 10/min
_last_call = [0.0]
_requests_spent = [0]

# Grupos del Mundial 2026 (sorteo 5-dic-2025 + repechajes marzo 2026).
# Nombres tal como suelen aparecer en API-Football; "candidatos" extra abajo.
GROUPS = {
    "A": ["Mexico", "South Korea", "South Africa", "Czech Republic"],
    "B": ["Canada", "Bosnia and Herzegovina", "Qatar", "Switzerland"],
    "C": ["Brazil", "Scotland", "Morocco", "Haiti"],
    "D": ["USA", "Turkey", "Australia", "Paraguay"],
    "E": ["Germany", "Curacao", "Ivory Coast", "Ecuador"],
    "F": ["Netherlands", "Japan", "Tunisia", "Sweden"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Cape Verde", "Saudi Arabia", "Uruguay"],
    "I": ["France", "Senegal", "Iraq", "Norway"],
    "J": ["Argentina", "Austria", "Algeria", "Jordan"],
    "K": ["Portugal", "Colombia", "Uzbekistan", "Congo DR"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

# Nombres alternativos con los que la API puede devolver cada equipo.
ALIASES = {
    "South Korea": ["South Korea", "Korea Republic"],
    "Czech Republic": ["Czech Republic", "Czechia"],
    "Bosnia and Herzegovina": ["Bosnia and Herzegovina", "Bosnia & Herzegovina", "Bosnia"],
    "USA": ["USA", "United States"],
    "Turkey": ["Turkey", "Turkiye"],
    "Ivory Coast": ["Ivory Coast", "Cote d'Ivoire"],
    "Cape Verde": ["Cape Verde Islands", "Cape Verde"],
    "Congo DR": ["Congo DR", "DR Congo", "Congo-Kinshasa"],
}

# Termino de busqueda cuando difiere del nombre (la API exige >=3 chars simples).
SEARCH_TERMS = {
    "South Korea": "Korea",
    "Congo DR": "Congo",
    "Bosnia and Herzegovina": "Bosnia",
    "USA": "usa",
}


def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().strip()


def api_get(path, cache_name):
    """GET con cache en disco y throttle. Devuelve el JSON de la respuesta."""
    cache_file = DATA / f"{cache_name}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text(encoding="utf-8"))
    wait = THROTTLE_SECONDS - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": API_KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    _last_call[0] = time.time()
    _requests_spent[0] += 1
    if payload.get("errors"):
        print(f"  !! error en {path}: {payload['errors']}", flush=True)
        return payload  # no cachear errores
    cache_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def candidates_for(team):
    return [norm(a) for a in ALIASES.get(team, [team])]


def main():
    all_teams = [t for group in GROUPS.values() for t in group]

    # 1) IDs via plantel del Mundial 2022 (1 request cubre ~26 equipos)
    print("[1/3] Equipos del Mundial 2022...", flush=True)
    wc22 = api_get("/teams?league=1&season=2022", "teams_wc2022")
    pool = {norm(item["team"]["name"]): item["team"] for item in wc22.get("response", [])}

    team_ids = {}
    missing = []
    for team in all_teams:
        hit = next((pool[c] for c in candidates_for(team) if c in pool), None)
        if hit:
            team_ids[team] = hit
        else:
            missing.append(team)
    print(f"  encontrados en WC2022: {len(team_ids)} | faltan: {missing}", flush=True)

    # 2) Busqueda individual para los que no jugaron el WC2022
    print("[2/3] Buscando equipos restantes...", flush=True)
    for team in missing:
        term = SEARCH_TERMS.get(team, team)
        res = api_get(f"/teams?search={urllib.request.quote(term)}", f"search_{norm(team).replace(' ', '_')}")
        cands = candidates_for(team)
        hit = None
        for item in res.get("response", []):
            t = item["team"]
            if t.get("national") and norm(t["name"]) in cands:
                hit = t
                break
        if not hit:  # fallback: primer resultado national que contenga el termino
            for item in res.get("response", []):
                t = item["team"]
                if t.get("national") and any(c in norm(t["name"]) for c in cands):
                    hit = t
                    break
        if hit:
            team_ids[team] = hit
            print(f"  {team} -> {hit['name']} (id {hit['id']})", flush=True)
        else:
            print(f"  !! NO ENCONTRADO: {team} (resultados: {[i['team']['name'] for i in res.get('response', [])][:8]})", flush=True)

    (DATA / "team_ids.json").write_text(
        json.dumps({k: v for k, v in team_ids.items()}, ensure_ascii=False, indent=1), encoding="utf-8")

    # 3) Partidos 2024 de cada equipo
    print("[3/3] Fixtures 2024 por equipo...", flush=True)
    summary = {}
    for i, team in enumerate(all_teams, 1):
        if team not in team_ids:
            print(f"  [{i:2}/48] {team}: SIN ID, se omite", flush=True)
            continue
        tid = team_ids[team]["id"]
        res = api_get(f"/fixtures?team={tid}&season=2024", f"fixtures_{tid}_2024")
        played = [f for f in res.get("response", [])
                  if f["fixture"]["status"]["short"] in ("FT", "AET", "PEN")]
        summary[team] = len(played)
        print(f"  [{i:2}/48] {team}: {len(played)} partidos jugados 2024", flush=True)

    print("\n=== RESUMEN ===", flush=True)
    print(f"equipos con ID: {len(team_ids)}/48 | requests gastados en esta corrida: {_requests_spent[0]}", flush=True)
    zeros = [t for t, n in summary.items() if n == 0]
    if zeros:
        print(f"ATENCION, equipos sin partidos 2024: {zeros}", flush=True)
    print("OK" if len(team_ids) == 48 and not zeros else "INCOMPLETO", flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
