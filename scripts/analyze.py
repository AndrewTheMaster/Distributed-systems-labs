#!/usr/bin/env python3
"""Aggregate experiment CSV files, render figures and Markdown tables (in Russian)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
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
    }
)


def load(name: str) -> pd.DataFrame:
    path = RES / name
    if not path.exists():
        raise SystemExit(f"missing {path}; run the experiments first")
    df = pd.read_csv(path)
    df["algorithm"] = df["algorithm"].astype(str)
    return df


def agg(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """Per-group means. p95 is averaged only over runs that reached 95 %."""
    valid = df[df["dissemination_ms_95"] >= 0]
    p95 = valid.groupby(keys)["dissemination_ms_95"].mean().rename("p95")
    out = df.groupby(keys).agg(
        coverage=("coverage_intended", "mean"),
        coverage_total=("coverage_total", "mean"),
        runs=("experiment_id", "size"),
        messages=("messages_sent", "mean"),
        dropped=("dropped", "mean"),
        send_errors=("send_errors", "mean"),
        reach95=("dissemination_ms_95", lambda x: (x >= 0).mean()),
    )
    out = out.join(p95, how="left")
    out["p95"] = out["p95"].fillna(-1.0)
    return out.reset_index()


def savefig(fig, name: str) -> None:
    path = IMG / name
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))


def line_plot(df, x, y, title, ylabel, xlabel, fname, logy=False, ylim=None):
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for alg in ORDER:
        cur = df[df.algorithm == alg].sort_values(x)
        if cur.empty:
            continue
        ys = cur[y].astype(float)
        if y == "p95":
            ys = ys.where(ys > 0)
        ax.plot(cur[x], ys, label=LABEL[alg], color=COLOR[alg], marker=MARKER[alg], linewidth=1.6, markersize=4.5)
    if logy:
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    if ylim:
        ax.set_ylim(*ylim)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=7.5, ncol=2, frameon=False)
    savefig(fig, fname)


def main() -> None:
    sim = load("sim_main.csv")
    topo = load("sim_topology.csv")
    scale = load("sim_scale.csv")
    crash = load("sim_crash.csv")
    docker = load("docker_main.csv")
    timeline = load("timeline.csv")

    sim_agg = agg(sim, ["algorithm", "loss", "fail_fraction"])
    topo_agg = agg(topo, ["algorithm", "topology"])
    scale_agg = agg(scale, ["algorithm", "nodes"])
    crash_agg = agg(crash, ["algorithm"])
    docker_agg = agg(docker, ["algorithm", "loss", "fail_fraction"])

    loss0 = sim_agg[sim_agg.fail_fraction == 0].copy()
    fail01 = sim_agg[sim_agg.loss == 0.1].copy()

    line_plot(
        loss0, "loss", "p95",
        "Время распространения (p95) при разных потерях пакетов",
        "p95, мс (лог. шкала)", "вероятность потери пакета", "loss_p95.png", logy=True,
    )
    line_plot(
        loss0, "loss", "coverage",
        "Покрытие целевых узлов при разных потерях пакетов",
        "покрытие (среднее)", "вероятность потери пакета", "loss_coverage.png", ylim=(-0.02, 1.05),
    )
    line_plot(
        loss0[loss0.algorithm.isin(["broadcast", "gossip_push", "gossip_pull", "rumor_mongering", "anti_entropy"])],
        "loss", "messages",
        "Накладные расходы при разных потерях пакетов",
        "сообщений за эксперимент (среднее, лог. шкала)", "вероятность потери пакета", "loss_messages.png", logy=True,
    )
    line_plot(
        fail01, "fail_fraction", "p95",
        "Время распространения (p95) при отказах узлов (потери 10 %)",
        "p95, мс (лог. шкала)", "доля отказавших узлов", "fail_p95.png", logy=True,
    )
    line_plot(
        fail01, "fail_fraction", "coverage_total",
        "Покрытие всех узлов при отказах (потери 10 %)",
        "покрытие всех узлов (среднее)", "доля отказавших узлов", "fail_coverage.png", ylim=(-0.02, 1.05),
    )

    # Topology: coverage and p95 side by side.
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 3.9))
    tops = ["random", "ring", "full"]
    tlabels = {"random": "random (степень 6)", "ring": "ring (степень 6)", "full": "full mesh"}
    algs = [a for a in ORDER if a in set(topo_agg.algorithm)]
    width = 0.8 / max(len(algs), 1)
    for ax, col, ylabel, title, logy in [
        (axes[0], "coverage", "покрытие (среднее)", "Покрытие по топологиям", False),
        (axes[1], "p95", "p95, мс (лог. шкала)", "p95 по топологиям (только успешные запуски)", True),
    ]:
        for i, alg in enumerate(algs):
            vals = []
            for t in tops:
                cur = topo_agg[(topo_agg.algorithm == alg) & (topo_agg.topology == t)]
                v = float(cur[col].iloc[0]) if not cur.empty else float("nan")
                if col == "p95" and v <= 0:
                    v = float("nan")
                vals.append(v)
            pos = [k + i * width - 0.4 + width / 2 for k in range(len(tops))]
            ax.bar(pos, vals, width=width, label=LABEL[alg], color=COLOR[alg])
        ax.set_xticks(range(len(tops)))
        ax.set_xticklabels([tlabels[t] for t in tops], fontsize=8)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        if logy:
            ax.set_yscale("log")
            ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
        else:
            ax.set_ylim(0, 1.05)
    axes[0].legend(fontsize=7, ncol=2, frameon=False, loc="lower left")
    savefig(fig, "topology.png")

    # Scale.
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for alg in ["broadcast", "gossip_push", "anti_entropy"]:
        cur = scale_agg[(scale_agg.algorithm == alg) & (scale_agg.p95 > 0)].sort_values("nodes")
        ax.plot(cur.nodes, cur.p95, marker=MARKER[alg], color=COLOR[alg], label=LABEL[alg], linewidth=1.6)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ticks = sorted(scale.nodes.unique())
    ax.set_xticks(ticks)
    ax.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.set_xlabel("число узлов (лог. шкала)")
    ax.set_ylabel("p95, мс (лог. шкала)")
    ax.set_title("Масштабирование: время p95 при потерях 10 % и отказах 10 %")
    ax.legend(fontsize=8, frameon=False)
    savefig(fig, "scale.png")

    # Crash during dissemination.
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    cr = crash_agg.set_index("algorithm").reindex([a for a in ORDER if a in set(crash_agg.algorithm)]).reset_index()
    bars = ax.bar([LABEL[a] for a in cr.algorithm], cr.coverage, color=[COLOR[a] for a in cr.algorithm])
    for b, v in zip(bars, cr.coverage):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01, f"{v:.3f}", ha="center", va="bottom", fontsize=8)
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("покрытие исходной популяции")
    ax.set_title("Авария 20 % узлов в момент t = 500 мс (потери 20 %)")
    ax.tick_params(axis="x", labelsize=7.5)
    savefig(fig, "crash.png")

    # Timeline.
    fig, ax = plt.subplots(figsize=(7.0, 4.0))
    for alg in ORDER:
        cur = timeline[timeline.algorithm == alg]
        if cur.empty:
            continue
        ax.plot(cur.time_ms, cur.coverage, color=COLOR[alg], label=LABEL[alg], linewidth=1.6)
    ax.set_xlabel("время, мс")
    ax.set_ylabel("покрытие целевых узлов")
    ax.set_ylim(-0.02, 1.05)
    ax.set_title("Рост покрытия во времени (120 узлов, потери 20 %, отказы 10 %, seed 1)")
    ax.legend(fontsize=7.5, frameon=False)
    savefig(fig, "timeline.png")

    # Docker vs simulation at loss 20 %, failures 20 %.
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
        if col == "p95":
            sv = [v if v > 0 else float("nan") for v in sv]
            dv = [v if v > 0 else float("nan") for v in dv]
        b1 = ax.bar([i - w / 2 for i in x], sv, w, label="симуляция (5 seed)", color="#9ecae1")
        b2 = ax.bar([i + w / 2 for i in x], dv, w, label="Docker, 110 контейнеров (2 seed)", color="#3182bd")
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

    # Docker network diagnostics at loss 0: what the application sent vs what
    # the kernels sent and received.
    d0 = docker[(docker.loss == 0) & (docker.fail_fraction == 0)]
    diag = d0.groupby("algorithm")[["messages_sent", "send_errors", "kernel_out", "kernel_in"]].mean()
    diag = diag.reindex([a for a in ORDER if a in diag.index])
    fig, ax = plt.subplots(figsize=(7.4, 3.9))
    x = list(range(len(diag)))
    w = 0.27
    ax.bar([i - w for i in x], diag.messages_sent, w, label="передано приложением", color="#9ecae1")
    ax.bar(x, diag.kernel_out, w, label="отправлено ядром (kernel_out)", color="#3182bd")
    ax.bar([i + w for i in x], diag.kernel_in, w, label="принято ядрами (kernel_in)", color="#08519c")
    ax.set_xticks(x)
    ax.set_xticklabels([LABEL[a] for a in diag.index], rotation=25, ha="right", fontsize=7)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(mticker.ScalarFormatter())
    ax.set_ylabel("датаграмм за эксперимент (среднее, лог.)")
    ax.set_title("Docker, потери 0 %: сколько датаграмм дошло до сети и до получателей")
    ax.legend(fontsize=7, frameon=False)
    savefig(fig, "docker_network.png")

    # ---- Tables -------------------------------------------------------
    out: list[str] = []
    name_ru = {a: LABEL[a] for a in ORDER}

    def fmt_row(r, cols, fmts):
        cells = []
        for c in cols:
            v = r[c]
            if c == "p95":
                cells.append("—" if v < 0 else f"{v:.0f}")
            elif c in fmts:
                cells.append(format(v, fmts[c]))
            else:
                cells.append(str(v))
        return "| " + " | ".join(cells) + " |"

    def table(df, cols, headers, fmts):
        lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
        for _, r in df.iterrows():
            rr = r.copy()
            if "algorithm" in rr.index:
                rr["algorithm"] = name_ru.get(rr["algorithm"], rr["algorithm"])
            lines.append(fmt_row(rr, cols, fmts))
        return "\n".join(lines) + "\n"

    f3 = {"coverage": ".3f", "coverage_total": ".3f", "reach95": ".2f", "messages": ".0f", "dropped": ".0f",
          "send_errors": ".0f", "loss": ".1f", "fail_fraction": ".1f", "nodes": "d", "dropped_": ".0f"}

    out.append("")
    out.append("Значения — средние по seed'ам. p95 — среднее только по запускам, где 95 % целевых узлов получили "
               "сообщение; reach95 — доля таких запусков; «—» — порог не достигнут ни в одном запуске. "
               "coverage — покрытие целевого множества; coverage_total — покрытие всех узлов, кроме источника.\n\n")

    out.append("## Таблица А.1. Потери пакетов, отказов нет (симуляция, 120 узлов)\n\n")
    out.append(table(loss0.sort_values(["algorithm", "loss"]),
                     ["algorithm", "loss", "coverage", "coverage_total", "p95", "reach95", "messages", "dropped"],
                     ["Алгоритм", "потери", "покрытие", "покрытие всех", "p95, мс", "reach95", "сообщений", "потеряно"],
                     f3))

    out.append("\n## Таблица А.2. Отказы узлов до старта, потери 10 % (симуляция)\n\n")
    out.append(table(fail01.sort_values(["algorithm", "fail_fraction"]),
                     ["algorithm", "fail_fraction", "coverage", "coverage_total", "p95", "reach95", "messages"],
                     ["Алгоритм", "доля отказов", "покрытие", "покрытие всех", "p95, мс", "reach95", "сообщений"],
                     f3))

    out.append("\n## Таблица А.3. Топологии, потери 10 %, отказы 10 % (симуляция)\n\n")
    out.append(table(topo_agg.sort_values(["algorithm", "topology"]),
                     ["algorithm", "topology", "coverage", "coverage_total", "p95", "reach95", "messages"],
                     ["Алгоритм", "топология", "покрытие", "покрытие всех", "p95, мс", "reach95", "сообщений"],
                     f3))

    out.append("\n## Таблица А.4. Масштабирование, потери 10 %, отказы 10 % (симуляция)\n\n")
    out.append(table(scale_agg.sort_values(["algorithm", "nodes"]),
                     ["algorithm", "nodes", "coverage", "p95", "reach95", "messages"],
                     ["Алгоритм", "узлов", "покрытие", "p95, мс", "reach95", "сообщений"], f3))

    out.append("\n## Таблица А.5. Авария 20 % узлов в t = 500 мс, потери 20 % (симуляция)\n\n")
    out.append(table(crash_agg.sort_values("algorithm"),
                     ["algorithm", "coverage", "coverage_total", "p95", "reach95", "messages"],
                     ["Алгоритм", "покрытие", "покрытие всех", "p95, мс", "reach95", "сообщений"], f3))

    out.append("\n## Таблица А.6. Docker (110 контейнеров): потери и отказы\n\n")
    out.append(table(docker_agg.sort_values(["algorithm", "loss", "fail_fraction"]),
                     ["algorithm", "loss", "fail_fraction", "coverage", "coverage_total", "p95", "reach95", "messages",
                      "dropped", "send_errors"],
                     ["Алгоритм", "потери", "отказы", "покрытие", "покрытие всех", "p95, мс", "reach95",
                      "сообщений", "потеряно", "ошибок отпр."], f3))

    # Kernel-level accounting per algorithm in the Docker runs.
    kacc = docker.groupby(["algorithm", "loss", "fail_fraction"]).agg(
        app_sent=("messages_sent", "mean"),
        send_errors=("send_errors", "mean"),
        kernel_out=("kernel_out", "mean"),
        kernel_in=("kernel_in", "mean"),
        sndbuf=("kernel_sndbuf_errors", "mean"),
        rcvbuf=("kernel_rcvbuf_errors", "mean"),
    ).reset_index()
    kacc["net_lost"] = kacc.kernel_out - kacc.kernel_in
    out.append("\n## Таблица А.7. Учёт датаграмм в Docker: приложение и ядро (среднее по seed'ам)\n\n")
    out.append("«Ошибок отпр.» — датаграммы, которые приложение не смогло передать ядру (ENOBUFS после IP_RECVERR); "
               "«отправлено ядром» — датаграммы, ушедшие из сокета узлов; «принято ядрами» — дошедшие до сокетов "
               "узлов; «потеряно в сети» = отправлено ядром − принято ядрами.\n\n")
    out.append(table(kacc.sort_values(["algorithm", "loss", "fail_fraction"]),
                     ["algorithm", "loss", "fail_fraction", "app_sent", "send_errors", "kernel_out", "kernel_in",
                      "net_lost", "sndbuf"],
                     ["Алгоритм", "потери", "отказы", "передано приложением", "ошибок отпр.",
                      "отправлено ядром", "принято ядрами", "потеряно в сети", "SndbufErrors"],
                     {"loss": ".1f", "fail_fraction": ".1f", "app_sent": ".0f", "send_errors": ".0f",
                      "kernel_out": ".0f", "kernel_in": ".0f", "net_lost": ".0f", "sndbuf": ".0f"}))

    (GEN / "tables.md").write_text("".join(out), encoding="utf-8")
    print("wrote", (GEN / "tables.md").relative_to(ROOT))

    summary = {
        "sim_main_runs": int(len(sim)),
        "sim_topology_runs": int(len(topo)),
        "sim_scale_runs": int(len(scale)),
        "sim_crash_runs": int(len(crash)),
        "sim_total_runs": int(len(sim) + len(topo) + len(scale) + len(crash)),
        "docker_runs": int(len(docker)),
        "docker_nodes": int(docker.nodes.max()),
        "sim_nodes_max": int(max(sim.nodes.max(), topo.nodes.max(), scale.nodes.max(), crash.nodes.max())),
        "docker_send_errors_total": int(docker.send_errors.sum()),
        "docker_kernel_out_total": int(docker.kernel_out.sum()),
        "docker_kernel_in_total": int(docker.kernel_in.sum()),
    }
    (GEN / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print("wrote", (GEN / "summary.json").relative_to(ROOT))


if __name__ == "__main__":
    main()
