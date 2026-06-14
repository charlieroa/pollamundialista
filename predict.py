# -*- coding: utf-8 -*-
"""Modelo de Poisson para la polla del Mundial 2026.

Calibra ataque/defensa de cada seleccion con sus partidos de 2024
(ultima temporada accesible en el plan Free de API-Football) y genera
grupos.html con la cuadricula de los 72 partidos de fase de grupos.
"""
import json
import math
import sys
from pathlib import Path

from fetch_data import GROUPS

DATA = Path(__file__).parent / "data"
OUT = Path(__file__).parent / "grupos.html"

MAX_GOALS = 6          # matriz de marcadores 0..6
SHRINK_K = 6           # suavizado: peso n/(n+K) hacia la media global
CLAMP = (0.55, 1.80)   # limites de fuerza ataque/defensa
HOST_BOOST = 1.10      # +10% de lambda para anfitriones en su grupo
HOSTS = {"Mexico", "USA", "Canada"}
RANK_WEIGHT = 0.65     # peso del ranking FIFA en la fuerza final
RANK_EXP = 0.38        # exponente goles<-Elo (suaviza la escala de puntos)

# Ranking FIFA al 10-jun-2026 (football-ranking.com); RD Congo estimado.
FIFA_POINTS = {
    "France": 1870.69, "Spain": 1873.87, "Argentina": 1876.11, "England": 1827.05,
    "Portugal": 1766.17, "Brazil": 1765.86, "Netherlands": 1753.57, "Belgium": 1742.23,
    "Germany": 1735.77, "Croatia": 1714.87, "Morocco": 1755.44, "Colombia": 1698.35,
    "Mexico": 1687.48, "Uruguay": 1673.07, "USA": 1671.24, "Switzerland": 1650.07,
    "Japan": 1661.58, "Senegal": 1685.24, "Iran": 1619.58, "South Korea": 1591.63,
    "Ecuador": 1598.51, "Austria": 1597.41, "Australia": 1579.34, "Canada": 1559.48,
    "Norway": 1557.44, "Panama": 1539.15, "Egypt": 1562.37, "Algeria": 1571.04,
    "Scotland": 1503.34, "Paraguay": 1505.35, "Tunisia": 1476.40, "Ivory Coast": 1540.87,
    "Uzbekistan": 1458.73, "Turkey": 1605.73, "Sweden": 1509.79, "Czech Republic": 1505.74,
    "South Africa": 1432.71, "Iraq": 1451.16, "New Zealand": 1275.58, "Ghana": 1346.88,
    "Bosnia and Herzegovina": 1387.22, "Jordan": 1387.73, "Cape Verde": 1371.11,
    "Haiti": 1293.09, "Curacao": 1294.77, "Congo DR": 1420.00, "Qatar": 1450.31,
    "Saudi Arabia": 1422.71,
}

NAMES_ES = {
    "Mexico": "México", "South Korea": "Corea del Sur", "South Africa": "Sudáfrica",
    "Czech Republic": "R. Checa", "Canada": "Canadá",
    "Bosnia and Herzegovina": "Bosnia", "Qatar": "Catar", "Switzerland": "Suiza",
    "Brazil": "Brasil", "Scotland": "Escocia", "Morocco": "Marruecos", "Haiti": "Haití",
    "USA": "EE.UU.", "Turkey": "Turquía", "Australia": "Australia", "Paraguay": "Paraguay",
    "Germany": "Alemania", "Curacao": "Curazao", "Ivory Coast": "C. de Marfil",
    "Ecuador": "Ecuador", "Netherlands": "P. Bajos", "Japan": "Japón",
    "Tunisia": "Túnez", "Sweden": "Suecia", "Belgium": "Bélgica", "Egypt": "Egipto",
    "Iran": "Irán", "New Zealand": "N. Zelanda", "Spain": "España",
    "Cape Verde": "Cabo Verde", "Saudi Arabia": "A. Saudita", "Uruguay": "Uruguay",
    "France": "Francia", "Senegal": "Senegal", "Iraq": "Irak", "Norway": "Noruega",
    "Argentina": "Argentina", "Austria": "Austria", "Algeria": "Argelia",
    "Jordan": "Jordania", "Portugal": "Portugal", "Colombia": "Colombia",
    "Uzbekistan": "Uzbekistán", "Congo DR": "RD Congo", "England": "Inglaterra",
    "Croatia": "Croacia", "Ghana": "Ghana", "Panama": "Panamá",
}

FLAGS = {
    "Mexico": "🇲🇽", "South Korea": "🇰🇷", "South Africa": "🇿🇦", "Czech Republic": "🇨🇿",
    "Canada": "🇨🇦", "Bosnia and Herzegovina": "🇧🇦", "Qatar": "🇶🇦", "Switzerland": "🇨🇭",
    "Brazil": "🇧🇷", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Morocco": "🇲🇦", "Haiti": "🇭🇹",
    "USA": "🇺🇸", "Turkey": "🇹🇷", "Australia": "🇦🇺", "Paraguay": "🇵🇾",
    "Germany": "🇩🇪", "Curacao": "🇨🇼", "Ivory Coast": "🇨🇮", "Ecuador": "🇪🇨",
    "Netherlands": "🇳🇱", "Japan": "🇯🇵", "Tunisia": "🇹🇳", "Sweden": "🇸🇪",
    "Belgium": "🇧🇪", "Egypt": "🇪🇬", "Iran": "🇮🇷", "New Zealand": "🇳🇿",
    "Spain": "🇪🇸", "Cape Verde": "🇨🇻", "Saudi Arabia": "🇸🇦", "Uruguay": "🇺🇾",
    "France": "🇫🇷", "Senegal": "🇸🇳", "Iraq": "🇮🇶", "Norway": "🇳🇴",
    "Argentina": "🇦🇷", "Austria": "🇦🇹", "Algeria": "🇩🇿", "Jordan": "🇯🇴",
    "Portugal": "🇵🇹", "Colombia": "🇨🇴", "Uzbekistan": "🇺🇿", "Congo DR": "🇨🇩",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Croatia": "🇭🇷", "Ghana": "🇬🇭", "Panama": "🇵🇦",
}

# Orden estandar de jornadas en un grupo de 4 (1 = cabeza de serie)
PAIRINGS = [(0, 1), (2, 3), (0, 2), (3, 1), (3, 0), (1, 2)]

# Calendario real de fase de grupos (local, visitante, fecha)
SCHEDULE = {
    "A": [("Mexico", "South Africa", "11 jun"), ("South Korea", "Czech Republic", "11 jun"),
          ("Czech Republic", "South Africa", "18 jun"), ("Mexico", "South Korea", "19 jun"),
          ("South Africa", "South Korea", "25 jun"), ("Czech Republic", "Mexico", "25 jun")],
    "B": [("Canada", "Bosnia and Herzegovina", "12 jun"), ("Qatar", "Switzerland", "13 jun"),
          ("Switzerland", "Bosnia and Herzegovina", "18 jun"), ("Canada", "Qatar", "19 jun"),
          ("Bosnia and Herzegovina", "Qatar", "24 jun"), ("Switzerland", "Canada", "24 jun")],
    "C": [("Brazil", "Morocco", "14 jun"), ("Haiti", "Scotland", "14 jun"),
          ("Scotland", "Morocco", "20 jun"), ("Brazil", "Haiti", "20 jun"),
          ("Scotland", "Brazil", "25 jun"), ("Morocco", "Haiti", "25 jun")],
    "D": [("USA", "Paraguay", "12 jun"), ("Australia", "Turkey", "14 jun"),
          ("USA", "Australia", "19 jun"), ("Turkey", "Paraguay", "20 jun"),
          ("Turkey", "USA", "26 jun"), ("Paraguay", "Australia", "26 jun")],
    "E": [("Germany", "Curacao", "14 jun"), ("Ivory Coast", "Ecuador", "15 jun"),
          ("Germany", "Ivory Coast", "20 jun"), ("Ecuador", "Curacao", "21 jun"),
          ("Ecuador", "Germany", "25 jun"), ("Curacao", "Ivory Coast", "25 jun")],
    "F": [("Netherlands", "Japan", "14 jun"), ("Sweden", "Tunisia", "15 jun"),
          ("Netherlands", "Sweden", "20 jun"), ("Tunisia", "Japan", "21 jun"),
          ("Japan", "Sweden", "26 jun"), ("Tunisia", "Netherlands", "26 jun")],
    "G": [("Belgium", "Egypt", "15 jun"), ("Iran", "New Zealand", "16 jun"),
          ("Belgium", "Iran", "21 jun"), ("New Zealand", "Egypt", "22 jun"),
          ("New Zealand", "Belgium", "27 jun"), ("Egypt", "Iran", "27 jun")],
    "H": [("Spain", "Cape Verde", "15 jun"), ("Saudi Arabia", "Uruguay", "16 jun"),
          ("Spain", "Saudi Arabia", "21 jun"), ("Uruguay", "Cape Verde", "22 jun"),
          ("Uruguay", "Spain", "27 jun"), ("Cape Verde", "Saudi Arabia", "27 jun")],
    "I": [("France", "Senegal", "16 jun"), ("Iraq", "Norway", "17 jun"),
          ("France", "Iraq", "22 jun"), ("Norway", "Senegal", "23 jun"),
          ("Senegal", "Iraq", "26 jun"), ("Norway", "France", "26 jun")],
    "J": [("Argentina", "Algeria", "17 jun"), ("Austria", "Jordan", "17 jun"),
          ("Argentina", "Austria", "22 jun"), ("Jordan", "Algeria", "23 jun"),
          ("Jordan", "Argentina", "28 jun"), ("Algeria", "Austria", "28 jun")],
    "K": [("Portugal", "Congo DR", "17 jun"), ("Uzbekistan", "Colombia", "18 jun"),
          ("Portugal", "Uzbekistan", "23 jun"), ("Colombia", "Congo DR", "24 jun"),
          ("Colombia", "Portugal", "28 jun"), ("Congo DR", "Uzbekistan", "28 jun")],
    "L": [("England", "Croatia", "17 jun"), ("Ghana", "Panama", "18 jun"),
          ("England", "Ghana", "23 jun"), ("Panama", "Croatia", "24 jun"),
          ("Croatia", "Ghana", "27 jun"), ("Panama", "England", "27 jun")],
}

# Resultados REALES jugados (clave = (local, visitante) tal cual en SCHEDULE).
# Actualizado al 13 jun 2026. Marca: 🎯 marcador exacto / ✔ resultado / atenuado = falló.
RESULTS = {
    ("Mexico", "South Africa"): (2, 0),          # 11 jun
    ("South Korea", "Czech Republic"): (2, 1),   # 11 jun (jugado un día antes de lo programado)
    ("Canada", "Bosnia and Herzegovina"): (1, 1),# 12 jun
    ("USA", "Paraguay"): (4, 1),                 # 12 jun (jugado un día antes de lo programado)
    ("Qatar", "Switzerland"): (1, 1),            # 13 jun
}


def expected_standings(st, mu):
    """Tabla esperada por grupo segun el calendario real: pts y dif. esperados."""
    standings = {}
    for g, fixtures in SCHEDULE.items():
        ep, egd = {}, {}
        for a, b, _ in fixtures:
            p = predict(a, b, st, mu)
            ep[a] = ep.get(a, 0.0) + 3 * p["p1"] + p["px"]
            ep[b] = ep.get(b, 0.0) + 3 * p["p2"] + p["px"]
            egd[a] = egd.get(a, 0.0) + p["la"] - p["lb"]
            egd[b] = egd.get(b, 0.0) + p["lb"] - p["la"]
        order = sorted(ep, key=lambda t: (ep[t], egd[t]), reverse=True)
        standings[g] = [(t, ep[t], egd[t]) for t in order]
    return standings


def best_thirds(standings):
    """Los 8 mejores terceros por puntos esperados."""
    thirds = sorted(((g, rows[2]) for g, rows in standings.items()),
                    key=lambda x: (x[1][1], x[1][2]), reverse=True)
    return [(g, row[0]) for g, row in thirds[:8]]


def load_team_stats():
    team_ids = json.loads((DATA / "team_ids.json").read_text(encoding="utf-8"))
    stats = {}
    for team, info in team_ids.items():
        tid = info["id"]
        gf = ga = n = 0
        seen = set()
        for f in sorted(DATA.glob(f"fixtures_{tid}_*.json")):
            for fx in json.loads(f.read_text(encoding="utf-8"))["response"]:
                fid = fx["fixture"]["id"]
                if fid in seen or fx["fixture"]["status"]["short"] not in ("FT", "AET", "PEN"):
                    continue
                seen.add(fid)
                gh, gaw = fx["goals"]["home"], fx["goals"]["away"]
                if gh is None or gaw is None:
                    continue
                if fx["teams"]["home"]["id"] == tid:
                    gf += gh; ga += gaw
                else:
                    gf += gaw; ga += gh
                n += 1
        if n:
            stats[team] = {"n": n, "gf": gf / n, "ga": ga / n}
    return stats


def strengths(stats):
    mu = sum(s["gf"] for s in stats.values()) / len(stats)
    mean_pts = sum(FIFA_POINTS.values()) / len(FIFA_POINTS)
    out = {}
    for team, s in stats.items():
        w = s["n"] / (s["n"] + SHRINK_K)  # poca muestra -> hacia la media
        atk_p = (s["gf"] / mu) * w + (1 - w)
        dfn_p = (s["ga"] / mu) * w + (1 - w)
        # fuerza implicada por el ranking FIFA (escala tipo Elo)
        elo = 10 ** ((FIFA_POINTS[team] - mean_pts) / 600)
        atk_r, dfn_r = elo ** RANK_EXP, elo ** -RANK_EXP
        atk = (1 - RANK_WEIGHT) * atk_p + RANK_WEIGHT * atk_r
        dfn = (1 - RANK_WEIGHT) * dfn_p + RANK_WEIGHT * dfn_r
        out[team] = {
            "atk": min(max(atk, CLAMP[0]), CLAMP[1]),
            "dfn": min(max(dfn, CLAMP[0]), CLAMP[1]),
            "n": s["n"], "gf": s["gf"], "ga": s["ga"], "pts": FIFA_POINTS[team],
        }
    return out, mu


def poisson(lmb, k):
    return math.exp(-lmb) * lmb ** k / math.factorial(k)


def predict(a, b, st, mu):
    la = st[a]["atk"] * st[b]["dfn"] * mu
    lb = st[b]["atk"] * st[a]["dfn"] * mu
    if a in HOSTS:
        la *= HOST_BOOST
    if b in HOSTS:
        lb *= HOST_BOOST
    pa = [poisson(la, k) for k in range(MAX_GOALS + 1)]
    pb = [poisson(lb, k) for k in range(MAX_GOALS + 1)]
    best, best_p, p_home, p_draw, p_away = (0, 0), 0.0, 0.0, 0.0, 0.0
    for i in range(MAX_GOALS + 1):
        for j in range(MAX_GOALS + 1):
            p = pa[i] * pb[j]
            if p > best_p:
                best, best_p = (i, j), p
            if i > j:
                p_home += p
            elif i == j:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away  # normalizar la masa truncada en 0..6
    return {
        "la": la, "lb": lb, "score": best, "p_score": best_p / total,
        "p1": p_home / total, "px": p_draw / total, "p2": p_away / total,
    }


def score_summary(st, mu):
    """Cuenta aciertos de resultado y de marcador exacto sobre lo ya jugado."""
    played = hits = exacts = 0
    for fixtures in SCHEDULE.values():
        for a, b, _ in fixtures:
            res = RESULTS.get((a, b))
            if not res:
                continue
            played += 1
            sa, sb = predict(a, b, st, mu)["score"]
            ra, rb = res
            if (sa, sb) == (ra, rb):
                exacts += 1; hits += 1
            elif ((sa > sb) - (sa < sb)) == ((ra > rb) - (ra < rb)):
                hits += 1
    return played, hits, exacts


def render(st, mu):
    standings = expected_standings(st, mu)
    qualified_thirds = {team for _, team in best_thirds(standings)}
    played, hits, exacts = score_summary(st, mu)
    rows = []
    for g, fixtures in SCHEDULE.items():
        cards = []
        for k, (a, b, date) in enumerate(fixtures):
            p = predict(a, b, st, mu)
            sa, sb = p["score"]
            fav = "home" if p["p1"] >= max(p["px"], p["p2"]) else ("draw" if p["px"] >= p["p2"] else "away")
            # Resultado real (si ya se jugó): clasifica el acierto y colorea
            res = RESULTS.get((a, b))
            mcls, badge = "", ""
            if res:
                ra, rb = res
                pred_sign = (sa > sb) - (sa < sb)
                real_sign = (ra > rb) - (ra < rb)
                if (sa, sb) == (ra, rb):
                    mcls, tag = "exact", "🎯 marcador exacto"
                elif pred_sign == real_sign:
                    mcls, tag = "hit", "✔ acertó resultado"
                else:
                    mcls, tag = "miss", "✗ falló"
                badge = (f'<div class="result"><span class="rscore">{ra} – {rb}</span>'
                         f'<span class="rtag">{tag}</span></div>')
            cards.append(f"""
      <div class="match {mcls}">
        <div class="mdate">J{k // 2 + 1} · {date}</div>
        <div class="teams">
          <span class="team {'fav' if fav == 'home' else ''}">{FLAGS[a]} {NAMES_ES[a]}</span>
          <span class="scorebox"><span class="score">{sa} – {sb}</span><span class="exact">prob. marcador {p['p_score'] * 100:.0f}%</span></span>
          <span class="team away {'fav' if fav == 'away' else ''}">{NAMES_ES[b]} {FLAGS[b]}</span>
        </div>{badge}
        <div class="bar">
          <div class="b1" style="width:{p['p1'] * 100:.1f}%"></div>
          <div class="bx" style="width:{p['px'] * 100:.1f}%"></div>
          <div class="b2" style="width:{p['p2'] * 100:.1f}%"></div>
        </div>
        <div class="probs">
          <span class="g1">Gana {NAMES_ES[a]} {p['p1'] * 100:.0f}%</span>
          <span class="gx">Empate {p['px'] * 100:.0f}%</span>
          <span class="g2">Gana {NAMES_ES[b]} {p['p2'] * 100:.0f}%</span>
        </div>
      </div>""")
        trs = ""
        for pos, (t, ep, gd) in enumerate(standings[g], 1):
            cls = "q1" if pos <= 2 else ("q3" if t in qualified_thirds else "")
            trs += (f"<tr class='{cls}'><td>{pos}</td><td>{FLAGS[t]} {NAMES_ES[t]}</td>"
                    f"<td>{ep:.1f}</td><td>{gd:+.1f}</td></tr>")
        rows.append(f"""
    <div class="group">
      <h2>Grupo {g}</h2>{''.join(cards)}
      <table class="standings">
        <tr><th>#</th><th>Posiciones (proyección)</th><th>Pts</th><th>Dif</th></tr>{trs}
      </table>
    </div>""")

    ranking = sorted(st.items(), key=lambda kv: kv[1]["atk"] - kv[1]["dfn"], reverse=True)
    table = "".join(
        f"<tr><td>{i}</td><td>{FLAGS[t]} {NAMES_ES[t]}</td><td>{s['atk']:.2f}</td>"
        f"<td>{s['dfn']:.2f}</td><td>{s['pts']:.0f}</td><td>{s['gf']:.2f}</td><td>{s['ga']:.2f}</td><td>{s['n']}</td></tr>"
        for i, (t, s) in enumerate(ranking, 1))

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Polla Mundial 2026 · Pronósticos Poisson</title>
<style>
  :root {{ --bg:#0d1117; --card:#161b22; --line:#30363d; --txt:#e6edf3; --dim:#8b949e;
          --c1:#2ea043; --cx:#8b949e; --c2:#d29922; }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--bg); color:var(--txt); font:15px/1.45 'Segoe UI',system-ui,sans-serif; padding:24px; }}
  h1 {{ font-size:26px; margin-bottom:4px; }}
  .sub {{ color:var(--dim); margin-bottom:24px; font-size:13px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(340px,1fr)); gap:16px; }}
  .group {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:14px 16px; }}
  .group h2 {{ font-size:15px; color:#58a6ff; margin-bottom:10px; letter-spacing:.5px; }}
  .match {{ padding:8px 0; border-top:1px solid var(--line); }}
  .match:first-of-type {{ border-top:none; }}
  .match.hit {{ background:rgba(46,160,67,.10); border-left:3px solid #2ea043; padding-left:8px; border-radius:4px; }}
  .match.exact {{ background:rgba(210,153,34,.14); border-left:3px solid #d29922; padding-left:8px; border-radius:4px; }}
  .match.miss {{ opacity:.6; }}
  .result {{ display:flex; align-items:center; justify-content:center; gap:8px; margin:4px 0 2px; font-size:11px; }}
  .rscore {{ background:#0d3a1a; color:#7ee787; font-weight:700; border-radius:5px; padding:1px 9px; }}
  .match.miss .rscore {{ background:#3a0d0d; color:#ff7b72; }}
  .match.exact .rscore {{ background:#3a2f0d; color:#f0c674; }}
  .rtag {{ color:var(--dim); }}
  .legend {{ display:flex; flex-wrap:wrap; gap:14px; align-items:center; margin:0 0 20px;
             padding:10px 14px; background:var(--card); border:1px solid var(--line); border-radius:8px; font-size:12.5px; }}
  .legend b {{ color:var(--txt); }}
  .chip {{ display:inline-flex; align-items:center; gap:5px; }}
  .sw {{ width:12px; height:12px; border-radius:3px; display:inline-block; }}
  .mdate {{ font-size:10.5px; color:var(--dim); text-align:center; margin-bottom:2px; }}
  .standings {{ width:100%; border-collapse:collapse; font-size:12px; margin-top:10px;
                border-top:2px solid var(--line); }}
  .standings th {{ color:var(--dim); text-align:left; font-weight:600; padding:4px 6px 2px; }}
  .standings td {{ padding:2px 6px; }}
  .standings tr.q1 td {{ color:#3fb950; font-weight:600; }}
  .standings tr.q3 td {{ color:#d29922; }}
  .teams {{ display:flex; align-items:center; gap:8px; }}
  .team {{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .team.away {{ text-align:right; }}
  .team.fav {{ font-weight:600; }}
  .scorebox {{ display:flex; flex-direction:column; align-items:center; gap:1px; }}
  .score {{ font-weight:700; font-size:17px; background:#21262d; border-radius:6px; padding:1px 10px; }}
  .exact {{ font-size:10px; color:#58a6ff; white-space:nowrap; }}
  .bar {{ display:flex; height:5px; border-radius:3px; overflow:hidden; margin:6px 0 3px; }}
  .b1 {{ background:var(--c1); }} .bx {{ background:var(--cx); }} .b2 {{ background:var(--c2); }}
  .probs {{ display:flex; justify-content:space-between; font-size:11.5px; color:var(--dim); }}
  .probs .g1 {{ color:var(--c1); }} .probs .g2 {{ color:var(--c2); }}
  table {{ border-collapse:collapse; margin-top:30px; font-size:13px; }}
  th,td {{ padding:4px 12px; text-align:left; border-bottom:1px solid var(--line); }}
  th {{ color:var(--dim); font-weight:600; }}
  .note {{ color:var(--dim); font-size:12px; margin-top:26px; max-width:760px; }}
</style>
</head>
<body>
<h1>⚽ Polla Mundial 2026 — Pronósticos Poisson</h1>
<p class="sub">Marcador más probable por partido (fase de grupos) · barras = prob. gana local / empate / gana visitante ·
calibrado con partidos internacionales de 2023–2024 (API-Football) · μ global = {mu:.2f} goles/partido ·
<a href="index.html" style="color:#58a6ff">ver plantilla de eliminatoria completa →</a></p>
<div class="legend">
  <b>Resultados reales hasta 13 jun:</b>
  <span class="chip"><span class="sw" style="background:#2ea043"></span> acertó resultado</span>
  <span class="chip"><span class="sw" style="background:#d29922"></span> 🎯 marcador exacto</span>
  <span class="chip" style="opacity:.6"><span class="sw" style="background:#6e7681"></span> falló</span>
  <span style="margin-left:auto; color:#7ee787"><b>{hits}/{played}</b> resultados · <b>{exacts}</b> marcador exacto</span>
</div>
<div class="grid">{''.join(rows)}
</div>
<h2 style="margin-top:34px">Fuerzas de los equipos (modelo)</h2>
<table>
<tr><th>#</th><th>Equipo</th><th>Ataque</th><th>Defensa</th><th>Pts FIFA</th><th>GF/p</th><th>GC/p</th><th>PJ</th></tr>
{table}
</table>
<p class="note"><b>Nota metodológica:</b> modelo de Poisson independiente por equipo. λ_A = ataque_A × defensa_B × μ
(cancha neutral; +10% para los anfitriones México, EE.UU. y Canadá). Las fuerzas combinan <b>65% ranking FIFA</b>
(10-jun-2026, escala tipo Elo) y <b>35% promedio de goles 2023–2024</b> (API-Football, plan gratuito), con suavizado
para muestras pequeñas — la parte de ranking corrige que los goles no ponderan la fuerza del rival. El "marcador" es la
celda más probable de la matriz 0–6 goles; aun siendo el más probable, rara vez supera el 15%: úsalo como guía, no como certeza.</p>
</body>
</html>"""
    OUT.write_text(html, encoding="utf-8")


def main():
    stats = load_team_stats()
    print(f"equipos con datos: {len(stats)}/48")
    st, mu = strengths(stats)
    print(f"media global de goles (mu): {mu:.3f}")
    top = sorted(st.items(), key=lambda kv: kv[1]['atk'] - kv[1]['dfn'], reverse=True)
    print("top 5 fuerza:", [(t, round(s['atk'], 2), round(s['dfn'], 2)) for t, s in top[:5]])
    print("bottom 5:", [(t, round(s['atk'], 2), round(s['dfn'], 2)) for t, s in top[-5:]])
    # sanity: probabilidades suman 1
    a, b = top[0][0], top[-1][0]
    p = predict(a, b, st, mu)
    assert abs(p['p1'] + p['px'] + p['p2'] - 1) < 1e-9
    print(f"ejemplo {a} vs {b}: {p['score']} ({p['p_score'] * 100:.0f}%), 1X2 = {p['p1']:.2f}/{p['px']:.2f}/{p['p2']:.2f}")
    render(st, mu)
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
