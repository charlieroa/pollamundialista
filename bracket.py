# -*- coding: utf-8 -*-
"""Plantilla de eliminatoria del Mundial 2026 estilo casa de apuestas.

Proyecta las tablas de grupos con puntos esperados (Poisson + ranking FIFA),
clasifica 1ro y 2do de cada grupo + los 8 mejores terceros, llena el cuadro
oficial de dieciseisavos y avanza al ganador mas probable hasta la final.
Genera index.html (vista principal del sitio).
"""
import datetime
import sys
from pathlib import Path

from predict import (FLAGS, MAX_GOALS, NAMES_ES, SCHEDULE, best_thirds,
                     expected_standings, load_team_stats, poisson, predict,
                     strengths)

OUT = Path(__file__).parent / "index.html"

# Cuadro oficial (Wikipedia/FIFA, partidos 73-104). 1X=ganador grupo,
# 2X=segundo, T<n>=mejor tercero asignado al partido n.
R32 = {
    73: ("2A", "2B"), 74: ("1E", "T74"), 75: ("1F", "2C"), 76: ("1C", "2F"),
    77: ("1I", "T77"), 78: ("2E", "2I"), 79: ("1A", "T79"), 80: ("1L", "T80"),
    81: ("1D", "T81"), 82: ("1G", "T82"), 83: ("2K", "2L"), 84: ("1H", "2J"),
    85: ("1B", "T85"), 86: ("1J", "2H"), 87: ("1K", "T87"), 88: ("2D", "2G"),
}
THIRD_SLOTS = {74: "ABCDF", 77: "CDFGH", 79: "CEFHI", 80: "EHIJK",
               81: "BEFIJ", 82: "AEHIJ", 85: "EFGIJ", 87: "DEIJL"}
R16 = {89: (74, 77), 90: (73, 75), 91: (76, 78), 92: (79, 80),
       93: (83, 84), 94: (81, 82), 95: (86, 88), 96: (85, 87)}
QF = {97: (89, 90), 98: (93, 94), 99: (91, 92), 100: (95, 96)}
SF = {101: (97, 98), 102: (99, 100)}

# Fecha y sede oficial de cada partido de eliminacion directa
KO_INFO = {
    73: ("28 jun", "Los Ángeles"), 74: ("29 jun", "Boston"), 75: ("29 jun", "Monterrey"),
    76: ("29 jun", "Houston"), 77: ("30 jun", "Nueva York/NJ"), 78: ("30 jun", "Dallas"),
    79: ("30 jun", "Ciudad de México"), 80: ("1 jul", "Atlanta"), 81: ("1 jul", "San Francisco"),
    82: ("1 jul", "Seattle"), 83: ("2 jul", "Toronto"), 84: ("2 jul", "Los Ángeles"),
    85: ("2 jul", "Vancouver"), 86: ("3 jul", "Miami"), 87: ("3 jul", "Kansas City"),
    88: ("3 jul", "Dallas"),
    89: ("4 jul", "Filadelfia"), 90: ("4 jul", "Houston"), 91: ("5 jul", "Nueva York/NJ"),
    92: ("5 jul", "Ciudad de México"), 93: ("6 jul", "Dallas"), 94: ("6 jul", "Seattle"),
    95: ("7 jul", "Atlanta"), 96: ("7 jul", "Vancouver"),
    97: ("9 jul", "Boston"), 98: ("10 jul", "Los Ángeles"),
    99: ("11 jul", "Miami"), 100: ("11 jul", "Kansas City"),
    101: ("14 jul", "Dallas"), 102: ("15 jul", "Atlanta"),
    104: ("19 jul", "Nueva York/NJ"),
}

# Disposicion visual: mitad izquierda alimenta la semifinal 101, derecha la 102
LEFT = {"r32": [74, 77, 73, 75, 83, 84, 81, 82], "r16": [89, 90, 93, 94], "qf": [97, 98], "sf": 101}
RIGHT = {"r32": [76, 78, 79, 80, 86, 88, 85, 87], "r16": [91, 92, 95, 96], "qf": [99, 100], "sf": 102}


def assign_thirds(best8):
    """Asigna los 8 mejores terceros a los slots permitidos (backtracking)."""
    slots = sorted(THIRD_SLOTS, key=lambda m: len(THIRD_SLOTS[m]))

    def bt(i, used, acc):
        if i == len(slots):
            return acc
        m = slots[i]
        for g, team in best8:
            if g in used or g not in THIRD_SLOTS[m]:
                continue
            r = bt(i + 1, used | {g}, {**acc, m: (g, team)})
            if r:
                return r
        return None

    sol = bt(0, set(), {})
    if sol:
        return sol
    return {m: best8[i] for i, m in enumerate(slots)}


def cuota(p):
    """Cuota decimal estilo casa de apuestas."""
    return f"{1 / max(p, 0.01):.2f}"


def main():
    stats = load_team_stats()
    st, mu = strengths(stats)
    standings = expected_standings(st, mu)

    firsts = {g: rows[0][0] for g, rows in standings.items()}
    seconds = {g: rows[1][0] for g, rows in standings.items()}
    best8 = best_thirds(standings)
    third_by_match = assign_thirds(best8)

    def resolve(slot):
        if slot.startswith("T"):
            return third_by_match[int(slot[1:])][1]
        kind, g = slot[0], slot[1]
        return firsts[g] if kind == "1" else seconds[g]

    def cond_score(la, lb, a_wins):
        total = best_p = 0.0
        best = (1, 0)
        for i in range(MAX_GOALS + 1):
            for j in range(MAX_GOALS + 1):
                pp = poisson(la, i) * poisson(lb, j)
                total += pp
                if i != j and (i > j) == a_wins and pp > best_p:
                    best, best_p = (i, j), pp
        return best, best_p / total

    # Avanzar el cuadro: gana el de mayor prob. (empate repartido 50/50, penales)
    entrants, winners, winprob, scores = {}, {}, {}, {}
    for m, (sa, sb) in R32.items():
        entrants[m] = (resolve(sa), resolve(sb))
    for rnd in (R32, R16, QF, SF, {104: (101, 102)}):
        for m, (xa, xb) in rnd.items():
            a, b = entrants[m] if m in entrants and rnd is R32 else (winners[xa], winners[xb])
            if rnd is not R32:
                entrants[m] = (a, b)
            p = predict(a, b, st, mu)
            pa = p["p1"] + 0.5 * p["px"]
            winners[m] = a if pa >= 0.5 else b
            winprob[m] = max(pa, 1 - pa)
            scores[m] = cond_score(p["la"], p["lb"], a_wins=(winners[m] == a))
    champion = winners[104]
    qualified_thirds = {team for _, team in best8}

    def slot_label(slot):
        if slot.startswith("T"):
            return f"3°({THIRD_SLOTS[int(slot[1:])]})"
        return f"{slot[0]}°{slot[1]}"

    labels = {m: f"{slot_label(sa)} vs {slot_label(sb)}" for m, (sa, sb) in R32.items()}
    for rnd in (R16, QF, SF, {104: (101, 102)}):
        for m, (xa, xb) in rnd.items():
            labels[m] = f"gana P{xa} vs gana P{xb}"

    def why_text(m):
        a, b = entrants[m]
        w = winners[m]
        loser = b if w == a else a
        p = predict(a, b, st, mu)
        lw, ll = (p["la"], p["lb"]) if w == a else (p["lb"], p["la"])
        (ga, gb), psc = scores[m]
        if st[w]["pts"] >= st[loser]["pts"]:
            razon = (f"mejor ranking FIFA ({st[w]['pts']:.0f} vs {st[loser]['pts']:.0f} pts) "
                     f"y más gol esperado ({lw:.1f} vs {ll:.1f})")
        else:
            razon = (f"aunque {NAMES_ES[loser]} tiene mejor ranking ({st[loser]['pts']:.0f} vs "
                     f"{st[w]['pts']:.0f} pts), el modelo le da más gol esperado "
                     f"({lw:.1f} vs {ll:.1f}) por sus resultados 2023–24")
        return (f"Gana {NAMES_ES[w]} por {razon}. Probabilidad de pasar: {winprob[m] * 100:.0f}% "
                f"(cuota {cuota(winprob[m])}). Marcador más probable si gana: "
                f"{max(ga, gb)}–{min(ga, gb)} ({psc * 100:.0f}% exacto).")

    def team_html(t, m, goals):
        won = winners[m] == t
        return (f"<div class='t {'win' if won else ''}'><span class='n'>{FLAGS[t]} {NAMES_ES[t]}</span>"
                f"<span class='gl'>{goals}</span></div>")

    def match_html(m, cls=""):
        a, b = entrants[m]
        w = winners[m]
        loser = b if w == a else a
        (ga, gb), psc = scores[m]
        wg, lg = max(ga, gb), min(ga, gb)
        date, city = KO_INFO.get(m, ("", ""))
        return (f"<div class='m {cls}'>"
                f"<div class='mhead'><span class='mnum'>P{m}</span>"
                f"<span class='mdate'>📅 {date} · {city}</span></div>"
                f"<div class='lbl'>{labels[m]}</div>"
                f"{team_html(a, m, ga)}{team_html(b, m, gb)}"
                f"<div class='sc'><span>Gana <b>{NAMES_ES[w]}</b> {wg}–{lg} a {NAMES_ES[loser]}</span>"
                f"<span class='odds'>{winprob[m] * 100:.0f}% · {cuota(winprob[m])}</span></div>"
                f"<div class='why'>{why_text(m)}</div></div>")

    def col_pairs(matches, label, side, incoming):
        mcls = f"in {side}" if incoming else ""
        pairs = "".join(
            f"<div class='pair {side}'><div class='slot'>{match_html(a, mcls)}</div>"
            f"<div class='slot'>{match_html(b, mcls)}</div></div>"
            for a, b in zip(matches[::2], matches[1::2]))
        return f"<div class='col'><div class='rnd'>{label}</div><div class='body'>{pairs}</div></div>"

    def col_single(m, label, side):
        return (f"<div class='col'><div class='rnd'>{label}</div><div class='body'>"
                f"<div class='slot'>{match_html(m, f'in out {side}')}</div></div></div>")

    def group_mini(g):
        cards = ""
        for k, (a, b, date) in enumerate(SCHEDULE[g]):
            p = predict(a, b, st, mu)
            sa, sb = p["score"]
            empate = p["px"] >= max(p["p1"], p["p2"])
            wt = None if empate else (a if p["p1"] > p["p2"] else b)
            res = "Empate" if empate else f"Gana {NAMES_ES[wt]}"
            pct = max(p["p1"], p["px"], p["p2"])
            rows = ""
            for t, goals in ((a, sa), (b, sb)):
                rows += (f"<div class='t {'win' if t == wt else ''}'>"
                         f"<span class='n'>{FLAGS[t]} {NAMES_ES[t]}</span>"
                         f"<span class='gl'>{goals}</span></div>")
            cards += (f"<div class='mg'><div class='mghead'><span>J{k // 2 + 1} · {date}</span>"
                      f"<span class='mgr'>{res} {pct * 100:.0f}%</span></div>{rows}</div>")
        q = [t for t, _, _ in [standings[g][0], standings[g][1]]]
        tercero = standings[g][2][0]
        pasan = f"Avanzan: <b>{NAMES_ES[q[0]]}</b> y <b>{NAMES_ES[q[1]]}</b>"
        if tercero in qualified_thirds:
            pasan += f" + {NAMES_ES[tercero]} (3°)"
        return f"<div class='gm'><div class='gmh'>GRUPO {g}</div>{cards}<div class='gmq'>{pasan}</div></div>"

    def col_groups(letters, label):
        slots = "".join(f"<div class='slot'>{group_mini(g)}</div>" for g in letters)
        return f"<div class='col gcol'><div class='rnd'>{label}</div><div class='body'>{slots}</div></div>"

    # ---- Fase de grupos: tarjetas con jornadas y clasificacion ----
    groups_html = ""
    for g, rows in standings.items():
        fx_rows = ""
        for k, (a, b, date) in enumerate(SCHEDULE[g]):
            p = predict(a, b, st, mu)
            sa, sb = p["score"]
            if p["px"] >= max(p["p1"], p["p2"]):
                res, pct = "Empate", p["px"]
            elif p["p1"] > p["p2"]:
                res, pct = f"Gana {NAMES_ES[a]}", p["p1"]
            else:
                res, pct = f"Gana {NAMES_ES[b]}", p["p2"]
            hoy = " · HOY" if date == "11 jun" else ""
            tip = (f"{NAMES_ES[a]} vs {NAMES_ES[b]} ({date}): {res} con {pct * 100:.0f}% "
                   f"(cuota {cuota(pct)}); marcador más probable {sa}–{sb} "
                   f"({p['p_score'] * 100:.0f}% exacto). Gana local {p['p1'] * 100:.0f}% / "
                   f"empate {p['px'] * 100:.0f}% / gana visitante {p['p2'] * 100:.0f}%")
            if k % 2 == 0:
                fx_rows += f"<div class='jor'>Jornada {k // 2 + 1}</div>"
            fx_rows += (f"<div class='fx' title='{tip}'>"
                        f"<span class='fd'>{date}{hoy}</span>"
                        f"<span class='fa'>{FLAGS[a]} {NAMES_ES[a]}</span>"
                        f"<span class='fs'>{sa}–{sb}</span>"
                        f"<span class='fb'>{NAMES_ES[b]} {FLAGS[b]}</span>"
                        f"<span class='fr'>{res} <b>{pct * 100:.0f}%</b></span></div>")
        trs = ""
        for pos, (t, ep, gd) in enumerate(rows, 1):
            cls = "q1" if pos <= 2 else ("q3" if t in qualified_thirds else "q0")
            tag = ("Clasifica" if pos <= 2 else
                   ("Mejor 3°" if t in qualified_thirds else "Eliminado"))
            trs += (f"<tr class='{cls}'><td>{pos}°</td><td>{FLAGS[t]} {NAMES_ES[t]}</td>"
                    f"<td>{ep:.1f}</td><td>{gd:+.1f}</td><td><span class='tag'>{tag}</span></td></tr>")
        groups_html += f"""
    <div class='g'>
      <div class='ghead'>GRUPO {g}</div>
      {fx_rows}
      <table>
        <tr><th>Pos</th><th>Equipo</th><th>Pts esp.</th><th>Dif.</th><th></th></tr>{trs}
      </table>
    </div>"""

    # ---- Banner HOY: partidos del dia (grupos y/o eliminatoria) ----
    MESES = {6: "jun", 7: "jul"}
    hoy_dt = datetime.date.today()
    hoy_str = f"{hoy_dt.day} {MESES.get(hoy_dt.month, '?')}"
    hoy_cards = ""
    for g, fixtures in SCHEDULE.items():
        for a, b, date in fixtures:
            if date != hoy_str:
                continue
            p = predict(a, b, st, mu)
            sa, sb = p["score"]
            if p["px"] >= max(p["p1"], p["p2"]):
                res, pct = "Empate", p["px"]
            else:
                wt = a if p["p1"] > p["p2"] else b
                res, pct = f"Gana {NAMES_ES[wt]}", max(p["p1"], p["p2"])
            hoy_cards += (f"<div class='today-m'><span class='tg'>Grupo {g}</span>"
                          f"<span class='tt'>{FLAGS[a]} {NAMES_ES[a]} <b>{sa}–{sb}</b> {NAMES_ES[b]} {FLAGS[b]}</span>"
                          f"<span class='tr'>{res} · {pct * 100:.0f}% · cuota {cuota(pct)}</span></div>")
    for m, (date, city) in KO_INFO.items():
        if date == hoy_str:
            a, b = entrants[m]
            (ga, gb), _ = scores[m]
            hoy_cards += (f"<div class='today-m'><span class='tg'>P{m} · {city}</span>"
                          f"<span class='tt'>{FLAGS[a]} {NAMES_ES[a]} <b>{ga}–{gb}</b> {NAMES_ES[b]} {FLAGS[b]}</span>"
                          f"<span class='tr'>Gana {NAMES_ES[winners[m]]} · {winprob[m] * 100:.0f}% · "
                          f"cuota {cuota(winprob[m])}</span></div>")
    today_html = ""
    if hoy_cards:
        today_html = (f"<div class='today'><div class='today-h'>🔴 HOY · {hoy_str}</div>{hoy_cards}</div>")

    bracket_html = (
        "<div class='bracket'>"
        + col_groups("ABCDEF", "Fase de grupos · 11–27 jun")
        + col_pairs(LEFT["r32"], "Dieciseisavos · 28 jun–3 jul", "l", incoming=False)
        + col_pairs(LEFT["r16"], "Octavos · 4–7 jul", "l", incoming=True)
        + col_pairs(LEFT["qf"], "Cuartos · 9–11 jul", "l", incoming=True)
        + col_single(LEFT["sf"], "Semifinal · 14 jul", "l")
        + (f"<div class='col final'><div class='rnd'>🏆 Final · 19 jul</div><div class='body'>"
           f"<div class='slot'><div style='width:100%;position:relative'>{match_html(104, 'fin')}"
           f"<div class='champ'><div class='champlbl'>CAMPEÓN PROYECTADO</div>"
           f"{FLAGS[champion]} {NAMES_ES[champion]}</div></div></div></div></div>")
        + col_single(RIGHT["sf"], "Semifinal · 15 jul", "r")
        + col_pairs(RIGHT["qf"], "Cuartos · 9–11 jul", "r", incoming=True)
        + col_pairs(RIGHT["r16"], "Octavos · 4–7 jul", "r", incoming=True)
        + col_pairs(RIGHT["r32"], "Dieciseisavos · 28 jun–3 jul", "r", incoming=False)
        + col_groups("GHIJKL", "Fase de grupos · 11–27 jun")
        + "</div>")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mundial 2026 · Plantilla de Pronósticos</title>
<style>
  :root {{ --bg:#0a0e14; --card:#121925; --card2:#0e141d; --line:#243044; --txt:#e8edf4;
          --dim:#7d8aa0; --green:#17c964; --gold:#f5a524; --blue:#3d9bff; --red:#f3415f; }}
  * {{ box-sizing:border-box; margin:0; }}
  body {{ background:var(--bg); color:var(--txt); font:13px/1.45 'Segoe UI',system-ui,sans-serif; }}
  a {{ color:var(--blue); text-decoration:none; }}

  header {{ background:linear-gradient(135deg,#101c2e 0%,#0d2818 55%,#101c2e 100%);
            border-bottom:1px solid var(--line); padding:20px 28px 16px; }}
  header h1 {{ font-size:23px; letter-spacing:.3px; }}
  header h1 span {{ color:var(--green); }}
  .sub {{ color:var(--dim); font-size:12.5px; margin-top:4px; }}
  .nav {{ margin-top:12px; display:flex; gap:8px; }}
  .nav a {{ background:#1b2940; border:1px solid var(--line); color:var(--txt);
            padding:5px 14px; border-radius:99px; font-size:12px; }}
  .nav a.on {{ background:var(--green); color:#04240f; font-weight:700; border-color:var(--green); }}

  main {{ padding:20px 24px 30px; }}
  .today {{ background:linear-gradient(90deg,#1c1023,#121925); border:1px solid #5b2740;
            border-radius:11px; padding:10px 16px; margin-bottom:20px; }}
  .today-h {{ font-size:11px; font-weight:800; letter-spacing:2px; color:var(--red); margin-bottom:6px; }}
  .today-m {{ display:flex; align-items:center; gap:14px; padding:3px 0; font-size:14px; }}
  .today-m .tg {{ font-size:9.5px; color:var(--dim); background:var(--card2); border:1px solid var(--line);
                  border-radius:99px; padding:1px 9px; white-space:nowrap; }}
  .today-m .tt b {{ background:var(--card2); border:1px solid var(--line); border-radius:6px;
                    padding:0 8px; margin:0 4px; }}
  .today-m .tr {{ margin-left:auto; font-size:11px; color:var(--green); font-weight:700; white-space:nowrap; }}
  h2.sec {{ font-size:15px; text-transform:uppercase; letter-spacing:1.5px; color:var(--gold);
            margin:6px 0 14px; display:flex; align-items:center; gap:10px; }}
  h2.sec::after {{ content:''; flex:1; height:1px; background:var(--line); }}

  /* ---------- bracket ---------- */
  .bracket {{ display:flex; gap:20px; overflow-x:auto; padding-bottom:14px; min-height:1150px; }}
  .col {{ display:flex; flex-direction:column; min-width:172px; flex:1; }}
  .rnd {{ height:30px; font-size:10.5px; color:var(--dim); text-align:center;
          text-transform:uppercase; letter-spacing:1px; font-weight:600; }}
  .body {{ flex:1; display:flex; flex-direction:column; }}
  .pair {{ flex:1; display:flex; flex-direction:column; position:relative; }}
  .pair::after {{ content:''; position:absolute; top:25%; height:50%; width:10px; right:-11px;
                  border:1px solid var(--line); border-left:none; border-radius:0 5px 5px 0; }}
  .pair.r::after {{ right:auto; left:-11px; border-left:1px solid var(--line); border-right:none;
                    border-radius:5px 0 0 5px; }}
  .slot {{ flex:1; display:flex; align-items:center; }}
  .m {{ width:100%; background:var(--card); border:1px solid var(--line); border-radius:9px;
        padding:6px 8px; position:relative; cursor:pointer; transition:border-color .15s, transform .15s; }}
  .m:hover {{ border-color:var(--green); transform:translateY(-1px); }}
  .m.in::before {{ content:''; position:absolute; top:50%; left:-11px; width:10px;
                   border-top:1px solid var(--line); }}
  .m.in.r::before {{ left:auto; right:-11px; }}
  .m.out::after {{ content:''; position:absolute; top:50%; right:-11px; width:10px;
                   border-top:1px solid var(--line); }}
  .m.out.r::after {{ right:auto; left:-11px; }}
  .m.fin::before, .m.fin::after {{ content:''; position:absolute; top:50%; width:10px;
                                    border-top:1px solid var(--line); }}
  .m.fin::before {{ left:-11px; }} .m.fin::after {{ right:-11px; }}
  .mhead {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:1px; }}
  .mnum {{ font-size:9px; color:var(--dim); background:var(--card2); border-radius:4px; padding:0 5px; }}
  .mdate {{ font-size:9.5px; color:var(--gold); font-weight:600; white-space:nowrap; }}
  .lbl {{ font-size:9px; color:var(--dim); margin-bottom:3px; }}
  .t {{ display:flex; align-items:center; gap:5px; padding:1.5px 0; color:var(--dim); }}
  .t .n {{ flex:1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; font-size:12.5px; }}
  .t.win {{ color:var(--txt); font-weight:700; }}
  .t .gl {{ min-width:20px; text-align:center; background:var(--card2); border-radius:5px;
            font-weight:700; border:1px solid var(--line); }}
  .t.win .gl {{ background:var(--green); color:#04240f; border-color:var(--green); }}
  .sc {{ display:flex; justify-content:space-between; align-items:center; gap:6px; flex-wrap:wrap;
         font-size:10.5px; color:var(--green); border-top:1px dashed var(--line);
         margin-top:4px; padding-top:3px; }}
  .odds {{ font-size:9.5px; color:#04240f; background:var(--green); border-radius:99px;
           padding:1px 7px; font-weight:700; white-space:nowrap; }}
  .m .why {{ display:none; font-size:10px; line-height:1.4; color:var(--dim); margin-top:4px;
             border-top:1px dashed var(--line); padding-top:4px; }}
  .m.open .why {{ display:block; }}
  .final .m {{ border-color:var(--gold); box-shadow:0 0 18px rgba(245,165,36,.12); }}
  .champ {{ position:absolute; top:100%; left:0; right:0; text-align:center; margin-top:12px;
            background:linear-gradient(135deg,#2a1f06,#1c1503); border:1px solid var(--gold);
            border-radius:9px; padding:7px 4px; font-size:17px; font-weight:800; color:var(--gold); }}
  .champlbl {{ font-size:8.5px; letter-spacing:2px; color:#b8860b; font-weight:600; }}

  /* ---------- mini-grupos en el bracket (mismas tarjetas) ---------- */
  .gcol {{ min-width:170px; flex:1; }}
  .gcol .body {{ gap:10px; }}
  .gm {{ width:100%; background:var(--card2); border:1px solid var(--line); border-radius:9px;
         padding:5px 7px 6px; }}
  .gmh {{ font-size:9.5px; font-weight:800; letter-spacing:1.5px; color:var(--blue); margin-bottom:3px; }}
  .mg {{ background:var(--card); border:1px solid var(--line); border-radius:7px;
         padding:3px 6px 4px; margin-bottom:4px; }}
  .mghead {{ display:flex; justify-content:space-between; gap:4px; font-size:8.5px;
             color:var(--dim); margin-bottom:1px; }}
  .mghead .mgr {{ color:var(--green); font-weight:700; white-space:nowrap; }}
  .mg .t {{ padding:0.5px 0; }}
  .mg .t .n {{ font-size:11px; }}
  .mg .t .gl {{ min-width:17px; font-size:11px; }}
  .gmq {{ font-size:9.5px; color:var(--green); margin-top:2px; line-height:1.35; }}
  .gmq b {{ font-weight:700; }}

  /* ---------- grupos ---------- */
  .groups {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(330px,1fr)); gap:14px; }}
  .g {{ background:var(--card); border:1px solid var(--line); border-radius:11px;
        padding:0 0 10px; overflow:hidden; }}
  .ghead {{ background:linear-gradient(90deg,#16233a,#121925); color:var(--blue); font-weight:800;
            letter-spacing:2px; font-size:12px; padding:8px 14px; border-bottom:1px solid var(--line); }}
  .jor {{ font-size:9px; color:var(--dim); text-transform:uppercase; letter-spacing:1.5px;
          padding:7px 14px 2px; }}
  .fx {{ display:flex; align-items:center; gap:6px; font-size:11.5px; padding:2.5px 14px; cursor:help; }}
  .fx:hover {{ background:var(--card2); }}
  .fx .fd {{ color:var(--dim); min-width:58px; font-size:9.5px; }}
  .fx .fa {{ flex:1.1; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .fx .fb {{ flex:1.1; text-align:right; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
  .fx .fs {{ font-weight:800; background:var(--card2); border:1px solid var(--line);
             border-radius:5px; padding:0 6px; }}
  .fx .fr {{ font-size:9px; color:var(--green); white-space:nowrap; min-width:92px; text-align:right; }}
  .g table {{ width:calc(100% - 28px); margin:9px 14px 0; border-collapse:collapse; font-size:11.5px;
              border-top:2px solid var(--line); }}
  .g th {{ color:var(--dim); text-align:left; font-weight:600; font-size:9.5px;
           text-transform:uppercase; letter-spacing:.5px; padding:6px 6px 3px; }}
  .g td {{ padding:3px 6px; border-top:1px solid #1a2436; }}
  .g tr.q1 td {{ color:var(--green); font-weight:600; }}
  .g tr.q3 td {{ color:var(--gold); }}
  .g tr.q0 td {{ color:var(--dim); }}
  .tag {{ font-size:8.5px; border:1px solid currentColor; border-radius:99px; padding:0 7px;
          text-transform:uppercase; letter-spacing:.5px; }}

  .note {{ color:var(--dim); font-size:11px; margin-top:22px; max-width:880px; line-height:1.5; }}
  .note b {{ color:var(--txt); }}
</style>
</head>
<body>
<header>
  <h1>🏆 Mundial 2026 <span>· Plantilla de Pronósticos</span></h1>
  <div class="sub">Modelo Poisson + ranking FIFA · 48 selecciones · 11 jun – 19 jul 2026 ·
  haz clic en cualquier llave para ver por qué gana</div>
  <div class="nav"><a class="on" href="index.html">Eliminatoria y grupos</a>
  <a href="grupos.html">Cuadrícula completa de grupos</a></div>
</header>
<main>
{today_html}
<h2 class="sec">Eliminación directa · empieza el 28 de junio</h2>
{bracket_html}
<h2 class="sec" style="margin-top:28px">Fase de grupos · 11–27 jun (proyección)</h2>
<div class="groups">{groups_html}</div>
<p class="note"><b>Cómo leer:</b> en la eliminatoria, cada llave muestra el partido oficial (número, fecha y sede),
qué clasificado llega (ej. "1°A vs 3°(CEFHI)" = ganador del grupo A contra un tercero de C/E/F/H/I) y el pronóstico en
verde: <b>quién gana, marcador y probabilidad con su cuota</b>. Haz clic en la llave para ver la explicación.
Los equipos mostrados son los que el modelo proyecta que llegan a cada llave — lo único fijo hoy son las llaves.
En los grupos, cada partido muestra fecha, marcador más probable y resultado; deja el mouse encima para el detalle 1X2.
<b>Modelo:</b> Poisson con fuerzas 65% ranking FIFA (10-jun-2026) + 35% goles 2023–24 (API-Football);
+10% de gol esperado para los anfitriones México, EE.UU. y Canadá; empates de eliminatoria repartidos 50/50 (penales).
Cuota = 1/probabilidad (referencia, no incluye margen de casa).</p>
</main>
<script>
document.querySelectorAll('.m').forEach(function(m) {{
  m.addEventListener('click', function() {{ m.classList.toggle('open'); }});
}});
</script>
</body>
</html>"""
    OUT.write_text(html, encoding="utf-8")
    print(f"campeon proyectado: {champion}")
    print("final:", entrants[104])
    print(f"OK -> {OUT}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
