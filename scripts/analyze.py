#!/usr/bin/env python3
"""Render the figures of docs/report.md from results/*.csv (means with 95 % CI)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

from report_tables import ci

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
IMG = ROOT / "docs" / "img"
IMG.mkdir(parents=True, exist_ok=True)

ORDER = ["unicast", "multicast", "broadcast", "gossip_push", "gossip_pull", "rumor_mongering", "anti_entropy"]
LABEL = {
    "unicast": "Unicast",
    "multicast": "Multicast",
    "broadcast": "Broadcast (flooding)",
    "gossip_push": "Gossip push",
    "gossip_pull": "Gossip pull",
    "rumor_mongering": "Rumor mongering",
    "anti_entropy": "Anti-entropy (push-pull)",
}
COLOR = {
    "unicast": "#6c757d",
    "multicast": "#8d6e63",
    "broadcast": "#d62728",
    "gossip_push": "#1f77b4",
    "gossip_pull": "#2ca02c",
    "rumor_mongering": "#ff7f0e",
    "anti_entropy": "#9467bd",
}
MARKER = {"unicast": "o", "multicast": "s", "broadcast": "D", "gossip_push": "^",
          "gossip_pull": "v", "rumor_mongering": "P", "anti_entropy": "X"}

plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 200,
    "font.family": "DejaVu Sans",
    "font.size": 9,
    "axes.titlesize": 10,
    "axes.labelsize": 9,
    "axes.grid": True,
    "grid.alpha": 0.25,
    "axes.spines.top": False,
    "axes.spines.right": False,
})


def load(name: str) -> pd.DataFrame:
    path = RES / name
    if not path.exists():
        raise SystemExit(f"missing {path}; run `make sim` first")
    df = pd.read_csv(path)
    df["algorithm"] = df["algorithm"].astype(str)
    return df


def agg(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per group: mean and 95 % half-width (*_hw) of coverage, coverage_total and p95.
    p95 is taken over runs that reached 95 %; other runs are excluded from p95 only."""
    rows = []
    for key, g in df.groupby(keys):
        key = key if isinstance(key, tuple) else (key,)
        rec = dict(zip(keys, key))
        for col, src in [("coverage", "coverage_intended"), ("coverage_total", "coverage_total")]:
            m, h, _ = ci(g[src])
            rec[col], rec[f"{col}_hw"] = m, h
        ok = g[g.dissemination_ms_95 >= 0]
        if len(ok):
            m, h, _ = ci(ok.dissemination_ms_95)
            rec["p95"], rec["p95_hw"] = m, h
        else:
            rec["p95"], rec["p95_hw"] = -1.0, 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def savefig(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(IMG / name, bbox_inches="tight")
    plt.close(fig)
    print("wrote", (IMG / name).relative_to(ROOT))


def line_plot(df, y, title, ylabel, xlabel, fname, x, logy=False, ylim=None):
    fig, ax = plt.subplots(figsize=(7.0, 4.2))
    for alg in ORDER:
        cur = df[df.algorithm == alg].sort_values(x)
        if cur.empty:
            continue
        ys = cur[y].astype(float)
        keep = ys > 0 if y == "p95" else ys.notna()
        ax.errorbar(cur[x][keep], ys[keep], yerr=cur[f"{y}_hw"][keep], label=LABEL[alg], color=COLOR[alg],
                    marker=MARKER[alg], linewidth=1.6, markersize=4.5, capsize=2, elinewidth=0.8)
    if logy:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=7.5, ncol=4, frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.2))
    savefig(fig, fname)


def main() -> None:
    sim = load("sim_main.csv")
    topo = load("sim_topology.csv")
    scale = load("sim_scale.csv")
    crash = load("sim_crash.csv")
    docker = load("docker_main.csv")

    sim_agg = agg(sim, ["algorithm", "loss", "fail_fraction"])
    loss0 = sim_agg[sim_agg.fail_fraction == 0]
    fail01 = sim_agg[sim_agg.loss == 0.1]

    line_plot(loss0, "p95", "Время распространения (p95) при разных потерях пакетов",
              "p95, мс (лог. шкала)", "вероятность потери пакета", "loss_p95.png", "loss", logy=True)
    line_plot(loss0, "coverage", "Покрытие целевых узлов при разных потерях пакетов",
              "покрытие (среднее)", "вероятность потери пакета", "loss_coverage.png", "loss", ylim=(-0.02, 1.05))
    line_plot(fail01, "coverage_total", "Покрытие всех узлов при отказах (потери 10 %)",
              "покрытие всех узлов (среднее)", "доля отказавших узлов", "fail_coverage.png", "fail_fraction",
              ylim=(-0.02, 1.05))

    # Scale.
    scale_agg = agg(scale, ["algorithm", "nodes"])
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for alg in ["broadcast", "gossip_push", "anti_entropy"]:
        cur = scale_agg[(scale_agg.algorithm == alg) & (scale_agg.p95 > 0)].sort_values("nodes")
        ax.errorbar(cur.nodes, cur.p95, yerr=cur.p95_hw, marker=MARKER[alg], color=COLOR[alg], label=LABEL[alg],
                    linewidth=1.6, capsize=2, elinewidth=0.8)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(sorted(scale.nodes.unique()))
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.set_xlabel("число узлов (лог. шкала)")
    ax.set_ylabel("p95, мс (лог. шкала)")
    ax.set_title("Масштабирование: время p95 при потерях 10 % и отказах 10 %")
    ax.legend(fontsize=8, frameon=False)
    savefig(fig, "scale.png")

    # Crash during dissemination.
    crash_agg = agg(crash, ["algorithm"])
    cr = crash_agg.set_index("algorithm").reindex([a for a in ORDER if a in set(crash_agg.algorithm)]).reset_index()
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    bars = ax.bar([LABEL[a] for a in cr.algorithm], cr.coverage, yerr=cr.coverage_hw, capsize=3,
                  color=[COLOR[a] for a in cr.algorithm])
    for b, v in zip(bars, cr.coverage):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("покрытие исходной популяции")
    ax.set_title("Авария 20 % узлов в момент t = 500 мс (потери 20 %)")
    ax.tick_params(axis="x", labelsize=7.5)
    savefig(fig, "crash.png")

    # Docker vs simulation at loss 20 %, failures 20 %.
    docker_agg = agg(docker, ["algorithm", "loss", "fail_fraction"])
    ds = docker_agg[(docker_agg.loss == 0.2) & (docker_agg.fail_fraction == 0.2)].set_index("algorithm")
    ss = sim_agg[(sim_agg.loss == 0.2) & (sim_agg.fail_fraction == 0.2)].set_index("algorithm")
    algs = [a for a in ORDER if a in ds.index or a in ss.index]
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.0))
    x = list(range(len(algs)))
    w = 0.38
    for ax, col, ylabel, title, logy in [
        (axes[0], "coverage", "покрытие (среднее)", "Покрытие: симуляция и Docker (потери 20 %, отказы 20 %)", False),
        (axes[1], "p95", "p95, мс (лог. шкала)", "p95: симуляция и Docker (только успешные запуски)", True),
    ]:
        sv = [float(ss.loc[a, col]) if a in ss.index else float("nan") for a in algs]
        dv = [float(ds.loc[a, col]) if a in ds.index else float("nan") for a in algs]
        sh = [float(ss.loc[a, col + "_hw"]) if a in ss.index else 0.0 for a in algs]
        dh = [float(ds.loc[a, col + "_hw"]) if a in ds.index else 0.0 for a in algs]
        if col == "p95":
            sv = [v if v > 0 else float("nan") for v in sv]
            dv = [v if v > 0 else float("nan") for v in dv]
        ax.bar([i - w / 2 for i in x], sv, w, yerr=sh, capsize=2, label="симуляция (30 seed)", color="#9ecae1")
        ax.bar([i + w / 2 for i in x], dv, w, yerr=dh, capsize=2, label="Docker, 110 контейнеров (5 seed)",
               color="#3182bd")
        ax.set_xticks(x)
        ax.set_xticklabels([LABEL[a] for a in algs], rotation=25, ha="right", fontsize=7)
        ax.set_title(title, fontsize=9)
        ax.set_ylabel(ylabel)
        if logy:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
        else:
            ax.set_ylim(0, 1.08)
        ax.legend(fontsize=7, frameon=False)
    savefig(fig, "docker_vs_sim.png")


if __name__ == "__main__":
    main()
