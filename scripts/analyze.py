#!/usr/bin/env python3
"""Aggregate experiment CSV files, render plots and Markdown tables."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"
IMG = ROOT / "docs" / "img"
GEN = ROOT / "docs" / "generated"
IMG.mkdir(parents=True, exist_ok=True)
GEN.mkdir(parents=True, exist_ok=True)

ORDER = [
    "unicast",
    "multicast",
    "broadcast",
    "gossip_push",
    "gossip_pull",
    "rumor_mongering",
    "anti_entropy",
]
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
MARKER = {
    "unicast": "o",
    "multicast": "s",
    "broadcast": "D",
    "gossip_push": "^",
    "gossip_pull": "v",
    "rumor_mongering": "P",
    "anti_entropy": "X",
}

plt.rcParams.update(
    {
        "figure.dpi": 160,
        "savefig.dpi": 160,
        "font.size": 9,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def load(name: str) -> pd.DataFrame:
    path = RES / name
    if not path.exists():
        raise SystemExit(f"missing {path}; run the experiments first")
    df = pd.read_csv(path)
    df["algorithm"] = df["algorithm"].astype(str)
    return df


def valid_p95(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["dissemination_ms_95"] >= 0]


def agg_valid(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    valid = valid_p95(df)
    g = valid.groupby(keys).agg(
        p95=("dissemination_ms_95", "mean"),
        p95_runs=("dissemination_ms_95", "size"),
    )
    allg = df.groupby(keys).agg(
        coverage=("coverage_intended", "mean"),
        coverage_total=("coverage_total", "mean"),
        runs=("experiment_id", "size"),
        messages=("messages_sent", "mean"),
        dropped=("dropped", "mean"),
    )
    out = allg.join(g, how="left")
    out["p95_reach"] = out["p95_runs"].fillna(0) / out["runs"]
    out["p95"] = out["p95"].fillna(-1)
    return out.reset_index()


def savefig(fig, name: str) -> None:
    path = IMG / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))


def line_plot(df, x, y, title, ylabel, fname, logy=False, ylim=None, filter_col=None, filter_val=None):
    sub = df if filter_col is None else df[df[filter_col] == filter_val]
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for alg in ORDER:
        cur = sub[sub.algorithm == alg]
        if cur.empty:
            continue
        cur = cur.sort_values(x)
        ys = cur[y].astype(float)
        if y == "p95":
            ys = ys.where(ys > 0)
        ax.plot(
            cur[x],
            ys,
            label=LABEL[alg],
            color=COLOR[alg],
            marker=MARKER[alg],
            linewidth=1.8,
            markersize=5,
        )
    if logy:
        ax.set_yscale("log")
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_xlabel(x.replace("_", " "))
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8, ncol=2)
    savefig(fig, fname)


def bar_plot(ax, df, value, ylabel, title, logy=False, annotate=True):
    algs = [a for a in ORDER if a in set(df.algorithm)]
    tops = [t for t in ["random", "ring", "full"] if t in set(df.topology)]
    if not tops:
        tops = sorted(set(df.topology))
    width = 0.8 / max(len(algs), 1)
    x = range(len(tops))
    for i, alg in enumerate(algs):
        vals = []
        for topo in tops:
            cur = df[(df.algorithm == alg) & (df.topology == topo)]
            v = cur[value].mean() if not cur.empty else float("nan")
            if value == "p95" and (pd.isna(v) or v < 0):
                v = float("nan")
            vals.append(v)
        pos = [p + i * width - 0.4 + width / 2 for p in x]
        bars = ax.bar(pos, vals, width=width, label=LABEL[alg], color=COLOR[alg])
        if annotate:
            for b, v in zip(bars, vals):
                if pd.isna(v):
                    continue
                ax.text(
                    b.get_x() + b.get_width() / 2,
                    b.get_height(),
                    f"{v:.2f}" if value != "p95" else f"{v:.0f}",
                    ha="center",
                    va="bottom",
                    fontsize=6.5,
                )
    ax.set_xticks(list(x))
    ax.set_xticklabels(tops)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    if logy:
        ax.set_yscale("log")
    ax.legend(fontsize=7, ncol=2)


def md_table(df: pd.DataFrame, cols: list[str], headers: list[str], floatfmt: dict[str, str] | None = None) -> str:
    floatfmt = floatfmt or {}
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                if pd.isna(v):
                    cells.append("—")
                elif c in floatfmt:
                    cells.append(format(v, floatfmt[c]))
                elif c in ("coverage", "coverage_total", "p95_reach"):
                    cells.append(f"{v:.3f}")
                else:
                    cells.append(f"{v:.1f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> None:
    sim = load("sim_main.csv")
    topo = load("sim_topology.csv")
    scale = load("sim_scale.csv")
    crash = load("sim_crash.csv")
    docker = load("docker_main.csv")
    timeline = load("timeline.csv")

    sim_agg = agg_valid(sim, ["algorithm", "loss", "fail_fraction"])
    topo_agg = agg_valid(topo, ["algorithm", "topology"])
    scale_agg = agg_valid(scale, ["algorithm", "nodes"])
    crash_agg = agg_valid(crash, ["algorithm"])
    docker_agg = agg_valid(docker, ["algorithm", "loss", "fail_fraction"])

    # Loss, no failures.
    loss0 = sim_agg[sim_agg.fail_fraction == 0].copy()
    line_plot(
        loss0,
        "loss",
        "p95",
        "Dissemination time (95%) vs packet loss",
        "p95, ms (log scale; only converged runs)",
        "loss_p95.png",
        logy=True,
    )
    line_plot(
        loss0,
        "loss",
        "coverage",
        "Coverage of intended recipients vs packet loss",
        "coverage (mean)",
        "loss_coverage.png",
        ylim=(-0.02, 1.05),
    )

    # Failures, 10% loss.
    fail01 = sim_agg[sim_agg.loss == 0.1].copy()
    line_plot(
        fail01,
        "fail_fraction",
        "p95",
        "Dissemination time (95%) vs failed nodes (loss=10%)",
        "p95, ms (log scale; only converged runs)",
        "fail_p95.png",
        logy=True,
    )
    line_plot(
        fail01,
        "fail_fraction",
        "coverage_total",
        "Coverage of all non-origin nodes vs failed nodes (loss=10%)",
        "coverage (mean)",
        "fail_coverage.png",
        ylim=(-0.02, 1.05),
    )

    # Messages.
    line_plot(
        loss0[loss0.algorithm.isin(["broadcast", "gossip_push", "gossip_pull", "rumor_mongering", "anti_entropy"])],
        "loss",
        "messages",
        "Protocol overhead vs packet loss",
        "messages sent per experiment (mean, log scale)",
        "loss_messages.png",
        logy=True,
    )

    # Topology.
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.1))
    bar_plot(axes[0], topo_agg, "coverage", "coverage", "Coverage by topology (loss=10%, failures=10%)")
    bar_plot(axes[1], topo_agg, "p95", "p95, ms (log)", "p95 by topology (only converged runs)", logy=True)
    savefig(fig, "topology.png")

    # Scale.
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for alg in ["broadcast", "gossip_push", "anti_entropy"]:
        cur = scale_agg[(scale_agg.algorithm == alg) & (scale_agg.p95 > 0)].sort_values("nodes")
        if cur.empty:
            continue
        ax.plot(
            cur.nodes,
            cur.p95,
            marker=MARKER[alg],
            color=COLOR[alg],
            label=LABEL[alg],
            linewidth=1.8,
        )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xticks(sorted(scale.nodes.unique()))
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("nodes")
    ax.set_ylabel("p95, ms (log)")
    ax.set_title("Scaling: 95% dissemination time vs cluster size (loss=10%, failures=10%)")
    ax.legend(fontsize=8)
    savefig(fig, "scale.png")

    # Crash.
    fig, ax = plt.subplots(figsize=(7.2, 4.0))
    crash_sorted = crash_agg.set_index("algorithm").reindex(
        [a for a in ORDER if a in set(crash_agg.algorithm)]
    ).reset_index()
    bars = ax.bar(
        [LABEL[a] for a in crash_sorted.algorithm],
        crash_sorted.coverage,
        color=[COLOR[a] for a in crash_sorted.algorithm],
    )
    for b, v in zip(bars, crash_sorted.coverage):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(), f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("coverage of initial population")
    ax.set_title("Coverage when 20% of nodes crash at t=500 ms (loss=20%)")
    ax.tick_params(axis="x", rotation=15)
    savefig(fig, "crash.png")

    # Timeline.
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    for alg in ORDER:
        cur = timeline[timeline.algorithm == alg]
        if cur.empty:
            continue
        ax.plot(
            cur.time_ms,
            cur.coverage,
            color=COLOR[alg],
            label=LABEL[alg],
            linewidth=1.8,
        )
    ax.set_xlabel("time, ms")
    ax.set_ylabel("coverage of intended recipients")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Coverage over time (120 nodes, loss=20%, failures=10%, seed=1)")
    ax.legend(fontsize=8)
    savefig(fig, "timeline.png")

    # Docker vs simulation.
    ds = docker_agg[(docker_agg.loss == 0.2) & (docker_agg.fail_fraction == 0.2)].set_index("algorithm")
    ss = sim_agg[(sim_agg.loss == 0.2) & (sim_agg.fail_fraction == 0.2)].set_index("algorithm")
    algs = [a for a in ORDER if a in ds.index or a in ss.index]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    x = range(len(algs))
    w = 0.38
    for ax, col, ylabel, title, logy in [
        (axes[0], "coverage", "coverage", "Coverage: simulation vs Docker (loss=20%, failures=20%)", False),
        (axes[1], "p95", "p95, ms (log)", "p95: simulation vs Docker (only converged runs)", True),
    ]:
        sv = [ss.loc[a, col] if a in ss.index else float("nan") for a in algs]
        dv = [ds.loc[a, col] if a in ds.index else float("nan") for a in algs]
        if col == "p95":
            sv = [v if v and v > 0 else float("nan") for v in sv]
            dv = [v if v and v > 0 else float("nan") for v in dv]
        b1 = ax.bar([i - w / 2 for i in x], sv, w, label="simulation", color="#9ecae1")
        b2 = ax.bar([i + w / 2 for i in x], dv, w, label="Docker (110)", color="#3182bd")
        ax.set_xticks(list(x))
        ax.set_xticklabels([LABEL[a] for a in algs], rotation=20, ha="right", fontsize=7.5)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        if logy:
            ax.set_yscale("log")
        elif col == "coverage":
            ax.set_ylim(0, 1.05)
        ax.legend(fontsize=8)
        for bars in (b1, b2):
            for b in bars:
                if b.get_height() > 0:
                    ax.text(
                        b.get_x() + b.get_width() / 2,
                        b.get_height(),
                        f"{b.get_height():.2f}" if col == "coverage" else f"{b.get_height():.0f}",
                        ha="center",
                        va="bottom",
                        fontsize=6,
                    )
    savefig(fig, "docker_vs_sim.png")

    # Markdown tables.
    out: list[str] = []
    out.append("# Сводные таблицы экспериментов\n")
    out.append("Все значения — средние по seed'ам. Для p95 указаны только запуски, где порог 95% был достигнут; "
               "`reach95` — доля таких запусков. `—` означает, что порог не был достигнут ни в одном запуске.\n")

    t = loss0[loss0.algorithm.isin(ORDER)].copy()
    t = t.sort_values(["algorithm", "loss"])
    out.append("\n## 1. Влияние потерь пакетов (отказов узлов нет)\n\n")
    out.append(
        md_table(
            t,
            ["algorithm", "loss", "coverage", "coverage_total", "p95", "p95_reach", "messages", "dropped"],
            ["Алгоритм", "loss", "coverage", "coverage_total", "p95, мс", "reach95", "сообщений", "drop"],
        )
    )

    t = fail01.copy().sort_values(["algorithm", "fail_fraction"])
    out.append("\n## 2. Влияние отказавших узлов (loss = 10%)\n\n")
    out.append(
        md_table(
            t,
            ["algorithm", "fail_fraction", "coverage", "coverage_total", "p95", "p95_reach", "messages"],
            ["Алгоритм", "доля отказов", "coverage", "coverage_total", "p95, мс", "reach95", "сообщений"],
        )
    )

    t = topo_agg.sort_values(["algorithm", "topology"])
    out.append("\n## 3. Влияние топологии (loss = 10%, failures = 10%)\n\n")
    out.append(
        md_table(
            t,
            ["algorithm", "topology", "coverage", "coverage_total", "p95", "p95_reach", "messages"],
            ["Алгоритм", "Топология", "coverage", "coverage_total", "p95, мс", "reach95", "сообщений"],
        )
    )

    t = scale_agg.sort_values(["algorithm", "nodes"])
    out.append("\n## 4. Масштабирование (loss = 10%, failures = 10%)\n\n")
    out.append(
        md_table(
            t,
            ["algorithm", "nodes", "coverage", "p95", "p95_reach", "messages"],
            ["Алгоритм", "Узлов", "coverage", "p95, мс", "reach95", "сообщений"],
        )
    )

    t = crash_agg.sort_values("algorithm")
    out.append("\n## 5. Отказ 20% узлов во время распространения (t = 500 мс, loss = 20%)\n\n")
    out.append(
        md_table(
            t,
            ["algorithm", "coverage", "coverage_total", "p95", "p95_reach", "messages"],
            ["Алгоритм", "coverage", "coverage_total", "p95, мс", "reach95", "сообщений"],
        )
    )

    t = docker_agg.sort_values(["algorithm", "loss", "fail_fraction"])
    out.append("\n## 6. Проверка на 110 Docker-контейнерах\n\n")
    out.append(
        md_table(
            t,
            ["algorithm", "loss", "fail_fraction", "coverage", "coverage_total", "p95", "p95_reach", "messages", "dropped"],
            ["Алгоритм", "loss", "fail", "coverage", "coverage_total", "p95, мс", "reach95", "сообщений", "drop"],
        )
    )

    (GEN / "tables.md").write_text("\n".join(out), encoding="utf-8")
    print("wrote", (GEN / "tables.md").relative_to(ROOT))

    summary = {
        "sim_main_rows": int(len(sim)),
        "docker_rows": int(len(docker)),
        "docker_nodes": int(docker.nodes.max()),
        "sim_nodes_max": int(max(sim.nodes.max(), topo.nodes.max(), scale.nodes.max(), crash.nodes.max())),
        "total_sim_runs": int(len(sim) + len(topo) + len(scale) + len(crash)),
        "total_docker_runs": int(len(docker)),
        "docker_send_errors": int(docker.send_errors.sum()),
    }
    (GEN / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", (GEN / "summary.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
