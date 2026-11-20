#!/usr/bin/env python3
"""Build the result tables of docs/report.md from results/*.csv.

Every number is a mean over seeds with a 95 % confidence half-width
(Student t, n-1 degrees of freedom). p95 is averaged over successful runs only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"

ORDER = ["unicast", "multicast", "broadcast", "gossip_push", "gossip_pull", "rumor_mongering", "anti_entropy"]
NAME = {
    "unicast": "Unicast",
    "multicast": "Multicast",
    "broadcast": "Broadcast",
    "gossip_push": "Gossip push",
    "gossip_pull": "Gossip pull",
    "rumor_mongering": "Rumor mongering",
    "anti_entropy": "Anti-entropy",
}


def load(name: str) -> pd.DataFrame:
    df = pd.read_csv(RES / name)
    df["algorithm"] = df["algorithm"].astype(str)
    return df


def ci(values) -> tuple[float, float, int] | None:
    x = pd.Series(values).dropna()
    n = len(x)
    if n == 0:
        return None
    mean = float(x.mean())
    if n < 2:
        return mean, 0.0, n
    half = float(stats.t.ppf(0.975, n - 1) * x.std(ddof=1) / n**0.5)
    return mean, half, n


def num(v: float, digits: int) -> str:
    return f"{v:.{digits}f}".replace(".", ",")


def pm(stat, digits: int = 0) -> str:
    if stat is None:
        return "-"
    mean, half, _ = stat
    if digits == 0 and abs(mean) < 10:
        digits = 1
    return f"{num(mean, digits)} ± {num(half, digits)}"


def p95_cell(df: pd.DataFrame) -> str:
    """p95 over runs that reached 95 %; notes the share of successful runs if < 100 %."""
    ok = df[df.dissemination_ms_95 >= 0]
    if ok.empty:
        return "-"
    cell = pm(ci(ok.dissemination_ms_95))
    share = len(ok) / len(df)
    if share < 1:
        cell += f" (в {round(share * 100)} % запусков)"
    return cell


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines)


def sel(df, algorithm, **conds) -> pd.DataFrame:
    out = df[df.algorithm == algorithm]
    for col, val in conds.items():
        out = out[out[col].round(6) == round(val, 6)]
    return out


def table_loss(sim: pd.DataFrame) -> str:
    rows = []
    for alg in ORDER:
        base = sel(sim, alg, loss=0.0, fail_fraction=0.0)
        hard = sel(sim, alg, loss=0.5, fail_fraction=0.0)
        rows.append([
            NAME[alg],
            p95_cell(base),
            p95_cell(hard) if not hard[hard.dissemination_ms_95 >= 0].empty else "-",
            pm(ci(hard.coverage_intended), 3),
            pm(ci(base.messages_sent)),
            pm(ci(hard.messages_sent)),
        ])
    return md_table(
        ["Алгоритм", "p95, потери 0 %, мс", "p95, потери 50 %, мс", "Покрытие, потери 50 %",
         "Сообщений, потери 0 %", "Сообщений, потери 50 %"],
        rows,
    )


def table_fail(sim: pd.DataFrame) -> str:
    rows = []
    for alg in ORDER:
        none = sel(sim, alg, loss=0.1, fail_fraction=0.0)
        high = sel(sim, alg, loss=0.1, fail_fraction=0.3)
        rows.append([
            NAME[alg],
            p95_cell(none),
            p95_cell(high),
            pm(ci(high.coverage_intended), 3),
            pm(ci(high.coverage_total), 3),
        ])
    return md_table(
        ["Алгоритм", "p95, отказов 0 %, мс", "p95, отказов 30 %, мс", "Покрытие целевых, отказов 30 %",
         "Покрытие всех, отказов 30 %"],
        rows,
    )


def table_topology(topo: pd.DataFrame) -> str:
    rows = []
    for alg in ["broadcast", "gossip_push", "gossip_pull", "anti_entropy"]:
        cells = [NAME[alg]]
        for t in ["random", "ring", "full"]:
            cur = topo[(topo.algorithm == alg) & (topo.topology == t)]
            cells.append(f"{p95_cell(cur)} / {pm(ci(cur.messages_sent))}")
        rows.append(cells)
    return md_table(["Алгоритм", "random, p95 / сообщений", "ring, p95 / сообщений", "full mesh, p95 / сообщений"], rows)


def table_scale(scale: pd.DataFrame) -> str:
    sizes = sorted(scale.nodes.unique())
    rows = []
    for alg in ["broadcast", "gossip_push", "anti_entropy"]:
        cells = [NAME[alg]]
        for n in sizes:
            cells.append(p95_cell(scale[(scale.algorithm == alg) & (scale.nodes == n)]))
        big = scale[(scale.algorithm == alg) & (scale.nodes == max(sizes))]
        cells.append(pm(ci(big.messages_sent)))
        rows.append(cells)
    return md_table(["Алгоритм"] + [f"{n} узлов, p95, мс" for n in sizes] + [f"Сообщений на {max(sizes)}"], rows)


def table_crash(crash: pd.DataFrame) -> str:
    rows = []
    for alg in ["broadcast", "gossip_push", "anti_entropy", "gossip_pull"]:
        cur = crash[crash.algorithm == alg]
        share = (cur.dissemination_ms_95 >= 0).mean()
        rows.append([NAME[alg], pm(ci(cur.coverage_intended), 3), p95_cell(cur), f"{num(share, 2)}"])
    return md_table(["Алгоритм", "Покрытие целевых", "p95, мс", "Доля запусков с p95"], rows)


def table_docker(dock: pd.DataFrame) -> str:
    rows = []
    for alg in ORDER:
        free = sel(dock, alg, loss=0.0, fail_fraction=0.0)
        lossy = sel(dock, alg, loss=0.4, fail_fraction=0.0)
        rows.append([
            NAME[alg],
            p95_cell(free),
            p95_cell(lossy) if not lossy[lossy.dissemination_ms_95 >= 0].empty else "-",
            pm(ci(lossy.coverage_intended), 3),
            pm(ci(lossy.messages_sent)),
        ])
    return md_table(
        ["Алгоритм", "p95, потери 0 %, мс", "p95, потери 40 %, мс", "Покрытие, потери 40 %", "Сообщений, потери 40 %"],
        rows,
    )


BUILDERS = {
    "loss": lambda: table_loss(load("sim_main.csv")),
    "fail": lambda: table_fail(load("sim_main.csv")),
    "topology": lambda: table_topology(load("sim_topology.csv")),
    "scale": lambda: table_scale(load("sim_scale.csv")),
    "crash": lambda: table_crash(load("sim_crash.csv")),
    "docker": lambda: table_docker(load("docker_main.csv")),
}


def inject(md: str) -> str:
    """Replace <!--T:name--> markers with generated tables."""
    def repl(m: re.Match) -> str:
        return "\n\n" + BUILDERS[m.group(1)]() + "\n\n"
    return re.sub(r"<!--T:(\w+)-->", repl, md)
