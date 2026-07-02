from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


st.set_page_config(
    page_title="Dashboard de Anomalias",
    page_icon=":bar_chart:",
    layout="wide",
)


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = BASE_DIR / "Data" / "recording_test_setupbox.xlsx"
BPMN_IMAGE = BASE_DIR / "BPMN-as-is.png"
PDD_PATH = BASE_DIR / "pdd-setupbox.md"
PROCESS_STEPS = [
    "fw_download",
    "bootloader",
    "kernel",
    "rootfs",
    "secure_boot",
    "mac_write",
    "wifi_cal",
    "bluetooth",
    "cable_scan",
    "hdmi_edid",
    "dvb_tuner",
    "drm_keys",
    "final_check",
]


@st.cache_data(show_spinner="Carregando arquivo...")
def load_data(path: Path):
    recordings = pd.read_excel(path, sheet_name="recordings")
    line_stops = pd.read_excel(path, sheet_name="line_stops")
    data_dictionary = pd.read_excel(path, sheet_name="data_dictionary")

    recordings["timestamp"] = pd.to_datetime(recordings["timestamp"], errors="coerce")
    line_stops["stop_start"] = pd.to_datetime(line_stops["stop_start"], errors="coerce")
    line_stops["stop_end"] = pd.to_datetime(line_stops["stop_end"], errors="coerce")

    return recordings, line_stops, data_dictionary


def get_options(data: pd.DataFrame, column: str):
    return sorted(data[column].dropna().unique().tolist())


def apply_multiselect_filter(data: pd.DataFrame, column: str, selected_values):
    if not selected_values:
        return data
    return data[data[column].isin(selected_values)]


def filter_recordings(data: pd.DataFrame, start_date, end_date, filters):
    filtered = data.copy()
    filtered = filtered[
        (filtered["timestamp"].dt.date >= start_date)
        & (filtered["timestamp"].dt.date <= end_date)
    ]

    for column, selected_values in filters.items():
        filtered = apply_multiselect_filter(filtered, column, selected_values)

    return filtered


def filter_line_stops(data: pd.DataFrame, start_date, end_date, selected_lines):
    filtered = data.copy()
    filtered = filtered[
        (filtered["stop_start"].dt.date <= end_date)
        & (filtered["stop_end"].dt.date >= start_date)
    ]

    if selected_lines:
        filtered = filtered[filtered["line"].isin(selected_lines)]

    return filtered


def build_pareto(data: pd.DataFrame, column: str):
    pareto = (
        data[column]
        .dropna()
        .value_counts()
        .rename_axis(column)
        .reset_index(name="count")
    )

    if pareto.empty:
        pareto["pct"] = []
        pareto["cum_pct"] = []
        return pareto

    pareto["pct"] = pareto["count"] / pareto["count"].sum()
    pareto["cum_pct"] = pareto["pct"].cumsum()
    return pareto


def plot_pareto(pareto: pd.DataFrame, column: str, title: str):
    fig = go.Figure()
    fig.add_bar(
        x=pareto[column],
        y=pareto["count"],
        name="Quantidade",
        text=pareto["count"],
        textposition="outside",
    )
    fig.add_scatter(
        x=pareto[column],
        y=pareto["cum_pct"],
        name="% acumulado",
        mode="lines+markers",
        yaxis="y2",
    )
    fig.add_hline(
        y=0.8,
        line_dash="dash",
        line_color="#777",
        yref="y2",
    )
    fig.update_layout(
        title=title,
        xaxis_title="",
        yaxis_title="Quantidade de falhas",
        yaxis2={
            "title": "% acumulado",
            "overlaying": "y",
            "side": "right",
            "tickformat": ".0%",
            "range": [0, 1.05],
        },
        legend={"orientation": "h", "y": 1.12},
        margin={"t": 80},
    )
    return fig


def format_pareto_table(pareto: pd.DataFrame):
    display_data = pareto.copy()
    display_data["pct"] = display_data["pct"].map("{:.2%}".format)
    display_data["cum_pct"] = display_data["cum_pct"].map("{:.2%}".format)
    return display_data


def add_main_defect_flags(data: pd.DataFrame):
    flagged = data.copy()
    flagged["is_fail"] = flagged["result"].eq("FAIL")
    flagged["is_main_defect"] = (
        flagged["failed_step"].eq("drm_keys")
        & flagged["error_code"].eq("ERR_DRM")
    )
    return flagged


def summarize_main_defect(data: pd.DataFrame, dimension: str):
    summary = (
        data.groupby(dimension, dropna=False)
        .agg(
            total_attempts=("result", "size"),
            total_failures=("is_fail", "sum"),
            main_defects=("is_main_defect", "sum"),
        )
        .reset_index()
    )
    summary["failure_rate"] = summary["total_failures"] / summary["total_attempts"]
    summary["main_defect_rate"] = (
        summary["main_defects"] / summary["total_attempts"]
    )
    summary["ppm_main_defect"] = summary["main_defect_rate"] * 1_000_000
    return summary.sort_values("main_defect_rate", ascending=False)


def available_ok_columns(data: pd.DataFrame):
    return [f"{step}_ok" for step in PROCESS_STEPS if f"{step}_ok" in data.columns]


def calculate_kpis(data: pd.DataFrame):
    total_attempts = len(data)
    total_serials = data["serial_number"].nunique()
    total_failures = data["result"].eq("FAIL").sum()

    attempt1 = data[data["attempt"].eq(1)].copy()
    first_pass_serials = attempt1.loc[
        attempt1["result"].eq("PASS"),
        "serial_number",
    ].nunique()

    if data.empty:
        final_pass_serials = 0
        reworked_serials = 0
        scrap_serials = 0
    else:
        serial_final = (
            data.groupby("serial_number")
            .agg(
                any_pass=("result", lambda values: values.eq("PASS").any()),
                max_attempt=("attempt", "max"),
                final_scrap=("disposition", lambda values: values.eq("SCRAP").any()),
            )
            .reset_index()
        )
        final_pass_serials = serial_final["any_pass"].sum()
        reworked_serials = serial_final["max_attempt"].gt(1).sum()
        scrap_serials = serial_final["final_scrap"].sum()

    ok_columns = available_ok_columns(data)
    opportunities = data[ok_columns].notna().sum().sum() if ok_columns else 0
    step_failures = data["failed_step"].notna().sum()

    min_time = data["timestamp"].min()
    max_time = data["timestamp"].max()
    elapsed_hours = (
        (max_time - min_time).total_seconds() / 3600
        if pd.notna(min_time) and pd.notna(max_time)
        else 0
    )
    station_count = data["station"].nunique()
    operator_count = data["operator"].nunique()

    fpy = first_pass_serials / total_serials if total_serials else 0
    final_yield = final_pass_serials / total_serials if total_serials else 0
    rework_rate = reworked_serials / total_serials if total_serials else 0
    scrap_rate = scrap_serials / total_serials if total_serials else 0
    unit_ppm = (1 - fpy) * 1_000_000 if total_serials else 0
    dpmo = step_failures / opportunities * 1_000_000 if opportunities else 0
    uph = final_pass_serials / elapsed_hours if elapsed_hours else 0
    uph_per_station = (
        final_pass_serials / (station_count * elapsed_hours)
        if station_count and elapsed_hours
        else 0
    )

    return {
        "total_attempts": total_attempts,
        "total_serials": total_serials,
        "total_failures": total_failures,
        "fpy": fpy,
        "final_yield": final_yield,
        "rework_rate": rework_rate,
        "scrap_rate": scrap_rate,
        "unit_ppm": unit_ppm,
        "dpmo": dpmo,
        "uph": uph,
        "uph_per_station": uph_per_station,
        "station_count": station_count,
        "operator_count": operator_count,
        "elapsed_hours": elapsed_hours,
    }


def build_serial_base(data: pd.DataFrame):
    attempt1 = data[data["attempt"].eq(1)].copy()
    if data.empty or attempt1.empty:
        return pd.DataFrame()

    serial_final = (
        data.groupby("serial_number")
        .agg(
            any_pass=("result", lambda values: values.eq("PASS").any()),
            max_attempt=("attempt", "max"),
            final_scrap=("disposition", lambda values: values.eq("SCRAP").any()),
        )
        .reset_index()
    )
    return attempt1.merge(serial_final, on="serial_number", how="left")


def yield_summary_by(data: pd.DataFrame, dimension: str):
    serial_base = build_serial_base(data)
    if serial_base.empty:
        return pd.DataFrame(
            columns=[
                dimension,
                "serials",
                "fpy",
                "final_yield",
                "rework_rate",
                "scrap_rate",
            ]
        )

    summary = (
        serial_base.groupby(dimension, dropna=False)
        .agg(
            serials=("serial_number", "nunique"),
            fpy=("result", lambda values: values.eq("PASS").mean()),
            final_yield=("any_pass", "mean"),
            rework_rate=("max_attempt", lambda values: values.gt(1).mean()),
            scrap_rate=("final_scrap", "mean"),
        )
        .reset_index()
        .sort_values("fpy")
    )
    return summary


def dpmo_by_step(data: pd.DataFrame):
    rows = []
    for step in PROCESS_STEPS:
        ok_column = f"{step}_ok"
        if ok_column not in data.columns:
            continue

        opportunities = data[ok_column].notna().sum()
        defects = data["failed_step"].eq(step).sum()
        defect_rate = defects / opportunities if opportunities else 0
        dpmo = defect_rate * 1_000_000
        rows.append(
            {
                "step": step,
                "opportunities": opportunities,
                "defects": defects,
                "defect_rate": defect_rate,
                "dpmo": dpmo,
            }
        )

    return pd.DataFrame(rows).sort_values("dpmo", ascending=False)


def jig_step_matrix(data: pd.DataFrame):
    if data.empty:
        return pd.DataFrame()

    counts = pd.crosstab(data["jig_id"], data["failed_step"])
    attempts = data.groupby("jig_id").size()
    return counts.div(attempts, axis=0).fillna(0)


def failure_time_by_line(data: pd.DataFrame):
    if data.empty:
        return pd.DataFrame()

    time_data = data.copy()
    time_data["is_fail"] = time_data["result"].eq("FAIL")
    summary = (
        time_data.set_index("timestamp")
        .groupby(["line", pd.Grouper(freq="30min")])
        .agg(total_attempts=("result", "size"), failures=("is_fail", "sum"))
        .query("total_attempts > 0")
        .reset_index()
    )
    summary["failure_rate"] = summary["failures"] / summary["total_attempts"]
    return summary


def main_defect_time(data: pd.DataFrame):
    analysis_data = add_main_defect_flags(data)
    if analysis_data.empty:
        return pd.DataFrame()

    summary = (
        analysis_data.set_index("timestamp")
        .groupby(pd.Grouper(freq="30min"))
        .agg(
            total_attempts=("result", "size"),
            total_failures=("is_fail", "sum"),
            main_defects=("is_main_defect", "sum"),
        )
        .query("total_attempts > 0")
        .reset_index()
    )
    summary["main_defect_rate"] = summary["main_defects"] / summary["total_attempts"]
    summary["failure_rate"] = summary["total_failures"] / summary["total_attempts"]
    summary["main_defect_rate_ma3"] = (
        summary["main_defect_rate"].rolling(3, min_periods=1).mean()
    )
    return summary


def availability_by_line(data: pd.DataFrame, stops: pd.DataFrame):
    if data.empty:
        return pd.DataFrame()

    line_window = (
        data.groupby("line")
        .agg(start=("timestamp", "min"), end=("timestamp", "max"))
        .reset_index()
    )
    line_window["planned_min_proxy"] = (
        line_window["end"] - line_window["start"]
    ) / pd.Timedelta(minutes=1)
    downtime = (
        stops.groupby("line")["duration_min"].sum().reset_index(name="downtime_min")
        if not stops.empty
        else pd.DataFrame(columns=["line", "downtime_min"])
    )
    availability = line_window.merge(downtime, on="line", how="left").fillna(
        {"downtime_min": 0}
    )
    availability["availability"] = (
        availability["planned_min_proxy"] - availability["downtime_min"]
    ) / availability["planned_min_proxy"]
    availability["downtime_rate"] = (
        availability["downtime_min"] / availability["planned_min_proxy"]
    )
    return availability.replace([float("inf"), -float("inf")], 0).fillna(0)


def downtime_by_reason(stops: pd.DataFrame):
    if stops.empty:
        return pd.DataFrame()

    return (
        stops.groupby(["line", "category", "reason"], dropna=False)
        .agg(stops=("reason", "size"), downtime_min=("duration_min", "sum"))
        .reset_index()
        .sort_values("downtime_min", ascending=False)
    )


def cycle_time_summary(data: pd.DataFrame):
    rows = []
    cycle_columns = [
        f"{step}_cycle_s" for step in PROCESS_STEPS if f"{step}_cycle_s" in data.columns
    ]
    for column in cycle_columns:
        step = column.replace("_cycle_s", "")
        values = data[column].dropna()
        if values.empty:
            continue

        q1 = values.quantile(0.25)
        q3 = values.quantile(0.75)
        iqr = q3 - q1
        threshold = q3 + 1.5 * iqr
        rows.append(
            {
                "step": step,
                "n": len(values),
                "mean_s": values.mean(),
                "median_s": values.median(),
                "p95_s": values.quantile(0.95),
                "max_s": values.max(),
                "outlier_threshold_s": threshold,
                "outliers": data[column].gt(threshold).sum(),
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    return df.sort_values("median_s", ascending=False)


def disposition_summary(data: pd.DataFrame):
    if data.empty:
        return pd.DataFrame(columns=["disposition", "attempts"])
    return (
        data["disposition"]
        .value_counts()
        .rename_axis("disposition")
        .reset_index(name="attempts")
    )


def scrap_by_defect(data: pd.DataFrame):
    scrap = data[data["disposition"].eq("SCRAP")]
    if scrap.empty:
        return pd.DataFrame()
    return (
        scrap.groupby(["failed_step", "error_code", "line"], dropna=False)
        .size()
        .reset_index(name="scrap_count")
        .sort_values("scrap_count", ascending=False)
    )


def remote_defect_data(data: pd.DataFrame):
    remote_data = data.copy()
    remote_data["is_remote_defect"] = (
        remote_data["failed_step"].eq("fw_download")
        | remote_data["error_code"].eq("ERR_AUTH")
    )
    return remote_data


def remote_summary(data: pd.DataFrame):
    remote_data = remote_defect_data(data)
    if remote_data.empty:
        return pd.DataFrame()

    summary = (
        remote_data.groupby(["line", "api_key"], dropna=False)
        .agg(total_attempts=("result", "size"), remote_defects=("is_remote_defect", "sum"))
        .reset_index()
    )
    summary["remote_defect_rate"] = (
        summary["remote_defects"] / summary["total_attempts"]
    )
    return summary.sort_values(["remote_defect_rate", "remote_defects"], ascending=False)


def remote_time_summary(data: pd.DataFrame):
    remote_data = remote_defect_data(data)
    if remote_data.empty:
        return pd.DataFrame()

    summary = (
        remote_data.set_index("timestamp")
        .groupby(["line", "api_key", pd.Grouper(freq="15min")])
        .agg(total_attempts=("result", "size"), remote_defects=("is_remote_defect", "sum"))
        .query("total_attempts >= 10")
        .reset_index()
    )
    summary["remote_defect_rate"] = (
        summary["remote_defects"] / summary["total_attempts"]
    )
    return summary.sort_values(["remote_defect_rate", "remote_defects"], ascending=False)


def bluetooth_summary(data: pd.DataFrame):
    bt_data = data[data["has_bluetooth"].eq(True)].copy()
    if bt_data.empty:
        return pd.DataFrame()

    bt_data["bt_fail"] = (
        bt_data["bluetooth_ok"].eq(False) | bt_data["failed_step"].eq("bluetooth")
    )
    summary = (
        bt_data.groupby(["line", "station", "jig_id", "model"], dropna=False)
        .agg(total_bt=("result", "size"), bt_fail=("bt_fail", "sum"))
        .reset_index()
    )
    summary["bt_fail_rate"] = summary["bt_fail"] / summary["total_bt"]
    return summary.sort_values(["bt_fail_rate", "bt_fail"], ascending=False)


def cable_summary(data: pd.DataFrame):
    cable_data = data[data["has_cable"].eq(True)].copy()
    if cable_data.empty:
        return pd.DataFrame(), pd.DataFrame()

    cable_data["cable_fail"] = (
        cable_data["cable_scan_ok"].eq(False)
        | cable_data["failed_step"].eq("cable_scan")
    )
    cable_data["zero_channels"] = cable_data["cable_channels_found"].eq(0)
    summary = (
        cable_data.groupby(["line", "station", "jig_id", "model"], dropna=False)
        .agg(
            total_cable=("result", "size"),
            cable_fail=("cable_fail", "sum"),
            zero_channels=("zero_channels", "sum"),
            avg_channels=("cable_channels_found", "mean"),
        )
        .reset_index()
    )
    summary["cable_fail_rate"] = summary["cable_fail"] / summary["total_cable"]
    summary["zero_channels_rate"] = summary["zero_channels"] / summary["total_cable"]
    zero_rows = cable_data[cable_data["zero_channels"]].sort_values("timestamp")
    return summary.sort_values(["zero_channels_rate", "zero_channels"], ascending=False), zero_rows


def integrity_checks(data: pd.DataFrame):
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()

    mac_serial_counts = (
        data.groupby("mac_address")["serial_number"].nunique().sort_values(ascending=False)
    )
    serial_mac_counts = (
        data.groupby("serial_number")["mac_address"].nunique().sort_values(ascending=False)
    )
    serial_attempt_counts = data.groupby("serial_number")["attempt"].agg(["count", "max"])
    summary = pd.DataFrame(
        [
            ["MACs usados por mais de um serial", int(mac_serial_counts.gt(1).sum())],
            ["Seriais com mais de um MAC", int(serial_mac_counts.gt(1).sum())],
            ["Seriais com rework legitimo", int(serial_attempt_counts["max"].gt(1).sum())],
            ["Seriais com mais de 2 registros", int(serial_attempt_counts["count"].gt(2).sum())],
        ],
        columns=["check", "count"],
    )

    bad_macs = mac_serial_counts[mac_serial_counts.gt(1)].index
    bad_mac_rows = data[data["mac_address"].isin(bad_macs)][
        [
            "timestamp",
            "mac_address",
            "serial_number",
            "line",
            "station",
            "jig_id",
            "operator",
            "model",
            "result",
            "disposition",
        ]
    ].sort_values(["mac_address", "timestamp"])
    return summary, bad_mac_rows


def build_markdown_report(kpis, pareto, main_defect, availability, cycle_data, scrap_data, integrity_summary, remote_data, bt_data, cable_data, integrity_bad_macs):
    top_defect = "Sem falhas no filtro atual"
    if not pareto.empty:
        top = pareto.iloc[0]
        top_defect = f"{top.iloc[0]} - {top['count']} ocorrências ({top['pct']:.2%})"

    main_start = main_defect["timestamp"].min() if not main_defect.empty else "N/A"
    main_end = main_defect["timestamp"].max() if not main_defect.empty else "N/A"
    bottleneck = "N/A"
    if not cycle_data.empty:
        row = cycle_data.iloc[0]
        bottleneck = f"{row['step']} - mediana {row['median_s']:.2f}s"

    lines = [
        "# Relatório do dashboard de anomalias",
        "",
        "## KPIs",
        f"- Tentativas: {kpis['total_attempts']:,}",
        f"- Seriais únicos: {kpis['total_serials']:,}",
        f"- Falhas: {kpis['total_failures']:,}",
        f"- FPY: {kpis['fpy']:.2%}",
        f"- Yield final: {kpis['final_yield']:.2%}",
        f"- Rework: {kpis['rework_rate']:.2%}",
        f"- Scrap: {kpis['scrap_rate']:.2%}",
        f"- PPM unidade: {kpis['unit_ppm']:,.0f}",
        f"- DPMO geral: {kpis['dpmo']:,.0f}",
        f"- UPH: {kpis['uph']:,.2f}",
        "",
        "## Pareto",
        f"- Maior defeito no filtro atual: {top_defect}",
        "",
        "## Defeito principal",
        f"- Par analisado: drm_keys + ERR_DRM",
        f"- Ocorrências no filtro atual: {len(main_defect):,}",
        f"- Janela: {main_start} até {main_end}",
        "",
        "## Downtime e disponibilidade",
    ]

    if availability.empty:
        lines.append("- Sem dados de disponibilidade no filtro atual.")
    else:
        for _, row in availability.iterrows():
            lines.append(
                f"- Linha {row['line']}: disponibilidade {row['availability']:.2%}, "
                f"downtime {row['downtime_min']:.1f} min"
            )

    lines.extend(["", "## Cycle time", f"- Gargalo por mediana: {bottleneck}", ""])

    lines.append("## Scrap")
    if scrap_data.empty:
        lines.append("- Sem scrap no filtro atual.")
    else:
        for _, row in scrap_data.head(5).iterrows():
            lines.append(
                f"- {row['failed_step']} / {row['error_code']} / linha {row['line']}: "
                f"{row['scrap_count']} scraps"
            )

    lines.extend(["", "## Acesso remoto (fw_download / ERR_AUTH)"])
    if remote_data.empty:
        lines.append("- Sem falhas de acesso remoto no filtro atual.")
    else:
        for _, row in remote_data.head(10).iterrows():
            lines.append(
                f"- Linha {row['line']} / API key {row['api_key']}: "
                f"taxa remota {row['remote_defect_rate']:.2%} "
                f"({int(row['remote_defects'])} falhas em {int(row['total_attempts'])} tentativas)"
            )

    lines.extend(["", "## Bluetooth"])
    if bt_data.empty:
        lines.append("- Sem falhas de Bluetooth no filtro atual.")
    else:
        for _, row in bt_data.head(10).iterrows():
            lines.append(
                f"- Linha {row['line']} / Estação {row['station']} / Jig {row['jig_id']} / Modelo {row['model']}: "
                f"taxa BT {row['bt_fail_rate']:.2%} "
                f"({int(row['bt_fail'])} falhas em {int(row['total_bt'])} tentativas)"
            )

    lines.extend(["", "## Cabo (0 canais)"])
    if cable_data.empty:
        lines.append("- Sem falhas de cabo no filtro atual.")
    else:
        for _, row in cable_data.head(10).iterrows():
            lines.append(
                f"- Linha {row['line']} / Estação {row['station']} / Jig {row['jig_id']} / Modelo {row['model']}: "
                f"taxa 0 canais {row['zero_channels_rate']:.2%} "
                f"({int(row['zero_channels'])} ocorrências em {int(row['total_cable'])} tentativas)"
            )

    lines.extend(["", "## Integridade"])
    if integrity_summary.empty:
        lines.append("- Sem dados de integridade no filtro atual.")
    else:
        for _, row in integrity_summary.iterrows():
            lines.append(f"- {row['check']}: {row['count']}")

    if not integrity_bad_macs.empty:
        lines.extend(["", "### MACs associados a mais de um serial"])
        for _, row in integrity_bad_macs.head(20).iterrows():
            lines.append(
                f"- MAC {row['mac_address']} / Serial {row['serial_number']} / "
                f"Linha {row['line']} / Jig {row['jig_id']} / "
                f"Timestamp {row['timestamp']}"
            )

    lines.extend(
        [
            "",
            "## Observação",
            "Relatório gerado a partir dos filtros aplicados no dashboard.",
        ]
    )
    return "\n".join(lines)


def format_time_window(start, end):
    if pd.isna(start) or pd.isna(end):
        return "janela não identificada"

    duration = end - start
    hours = duration.total_seconds() / 3600
    if hours >= 1:
        duration_text = f"{hours:.1f}h"
    else:
        duration_text = f"{duration.total_seconds() / 60:.0f}min"

    return f"{start:%d/%m %H:%M} até {end:%d/%m %H:%M} ({duration_text})"


def most_common_value(data: pd.DataFrame, column: str):
    values = data[column].dropna()
    if values.empty:
        return "N/A"
    return values.mode().iloc[0]


def build_key_findings(data: pd.DataFrame):
    if data.empty:
        return ["Sem registros para os filtros atuais."]

    findings = []
    failures = data[data["result"].eq("FAIL")]

    if not failures.empty:
        top_step = failures["failed_step"].dropna().value_counts()
        top_error = failures["error_code"].dropna().value_counts()
        if not top_step.empty and not top_error.empty:
            step_name = top_step.index[0]
            error_name = top_error.index[0]
            step_share = top_step.iloc[0] / len(failures)
            error_share = top_error.iloc[0] / len(failures)
            findings.append(
                f"O maior volume de falha está em {step_name} ({step_share:.1%}); "
                f"o erro mais frequente é {error_name} ({error_share:.1%})."
            )

    analysis_data = add_main_defect_flags(data)
    main_defect = analysis_data[analysis_data["is_main_defect"]]
    if not main_defect.empty:
        line = most_common_value(main_defect, "line")
        station = most_common_value(main_defect, "station")
        jig = most_common_value(main_defect, "jig_id")
        firmware = most_common_value(main_defect, "firmware_version")
        window = format_time_window(
            main_defect["timestamp"].min(),
            main_defect["timestamp"].max(),
        )
        findings.append(
            f"DRM é o defeito que mais chama atenção: {len(main_defect):,} casos, "
            f"principalmente em {line} / {station} / {jig}, firmware {firmware}, de {window}."
        )

    remote_data = remote_summary(data)
    if not remote_data.empty:
        row = remote_data.iloc[0]
        findings.append(
            f"Falha remota aparece mais em {row['line']} com a API key {row['api_key']} "
            f"({row['remote_defect_rate']:.1%})."
        )

    cable_data, zero_channel_rows = cable_summary(data)
    if not zero_channel_rows.empty:
        window = format_time_window(
            zero_channel_rows["timestamp"].min(),
            zero_channel_rows["timestamp"].max(),
        )
        findings.append(
            f"Foram encontrados {len(zero_channel_rows):,} casos com 0 canais no cabo, de {window}."
        )

    _, bad_mac_rows = integrity_checks(data)
    if not bad_mac_rows.empty:
        bad_mac_count = bad_mac_rows["mac_address"].nunique()
        findings.append(
            f"Integridade precisa de atenção: {bad_mac_count:,} MAC(s) aparecem em mais de um serial."
        )

    return findings[:5] if findings else ["Nenhum ponto crítico apareceu com os filtros atuais."]


st.title("Dashboard de Anomalias")
st.caption("Análise do teste de gravação de setupboxes, com filtros, KPIs, falhas e auditoria.")

if not DATA_PATH.exists():
    st.error(f"Arquivo não encontrado: {DATA_PATH}")
    st.stop()

recordings, line_stops, data_dictionary = load_data(DATA_PATH)

min_date = recordings["timestamp"].dt.date.min()
max_date = recordings["timestamp"].dt.date.max()


with st.sidebar:
    st.header("Filtros")
    st.success("Arquivo carregado")
    st.caption(DATA_PATH.name)

    date_range = st.date_input(
        "Periodo",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date

    selected_filters = {
        "line": st.multiselect("Linha", get_options(recordings, "line")),
        "station": st.multiselect("Estação", get_options(recordings, "station")),
        "jig_id": st.multiselect("Jig", get_options(recordings, "jig_id")),
        "operator": st.multiselect("Operador", get_options(recordings, "operator")),
        "shift": st.multiselect("Turno", get_options(recordings, "shift")),
        "model": st.multiselect("Modelo", get_options(recordings, "model")),
        "firmware_version": st.multiselect(
            "Firmware",
            get_options(recordings, "firmware_version"),
        ),
        "result": st.multiselect("Resultado", get_options(recordings, "result")),
        "disposition": st.multiselect(
            "Disposition",
            get_options(recordings, "disposition"),
        ),
        "error_code": st.multiselect(
            "Código de erro",
            get_options(recordings, "error_code"),
        ),
    }


filtered_recordings = filter_recordings(
    recordings,
    start_date,
    end_date,
    selected_filters,
)
filtered_line_stops = filter_line_stops(
    line_stops,
    start_date,
    end_date,
    selected_filters["line"],
)
filtered_kpis = calculate_kpis(filtered_recordings)


tab_overview, tab_failures, tab_time, tab_audit, tab_docs = st.tabs(
    [
        "Visão geral",
        "Falhas",
        "Tempo e paradas",
        "Auditoria",
        "BPMN e PDD",
    ]
)


with tab_overview:
    st.subheader("Base carregada")

    col1, col2, col3 = st.columns(3)
    col1.metric("recordings", f"{len(recordings):,} linhas")
    col2.metric("line_stops", f"{len(line_stops):,} linhas")
    col3.metric("data_dictionary", f"{len(data_dictionary):,} linhas")

    st.subheader("Recorte atual")
    col1, col2, col3 = st.columns(3)
    col1.metric("Registros filtrados", f"{len(filtered_recordings):,}")
    col2.metric("Seriais únicos", f"{filtered_recordings['serial_number'].nunique():,}")
    col3.metric("Paradas filtradas", f"{len(filtered_line_stops):,}")

    st.subheader("KPIs gerais")
    row1 = st.columns(4)
    row1[0].metric("Tentativas", f"{filtered_kpis['total_attempts']:,}")
    row1[1].metric("Seriais únicos", f"{filtered_kpis['total_serials']:,}")
    row1[2].metric("Falhas", f"{filtered_kpis['total_failures']:,}")
    row1[3].metric("FPY", f"{filtered_kpis['fpy']:.2%}")

    row2 = st.columns(4)
    row2[0].metric("Yield final", f"{filtered_kpis['final_yield']:.2%}")
    row2[1].metric("Rework", f"{filtered_kpis['rework_rate']:.2%}")
    row2[2].metric("Scrap", f"{filtered_kpis['scrap_rate']:.2%}")
    row2[3].metric("PPM unidade", f"{filtered_kpis['unit_ppm']:,.0f}")

    row3 = st.columns(4)
    row3[0].metric("DPMO geral", f"{filtered_kpis['dpmo']:,.0f}")
    row3[1].metric("UPH", f"{filtered_kpis['uph']:,.2f}")
    row3[2].metric("UPH por estação", f"{filtered_kpis['uph_per_station']:,.2f}")
    row3[3].metric("Horas observadas", f"{filtered_kpis['elapsed_hours']:,.2f}")

    st.subheader("Resumo dos achados")
    for finding in build_key_findings(filtered_recordings):
        st.markdown(f"- {finding}")

    st.subheader("Yield por dimensão")
    yield_dimension = st.selectbox(
        "Dimensão do yield",
        ["line", "station", "model", "firmware_version"],
        format_func={
            "line": "Linha",
            "station": "Estação",
            "model": "Modelo",
            "firmware_version": "Firmware",
        }.get,
    )
    yield_data = yield_summary_by(filtered_recordings, yield_dimension)

    if yield_data.empty:
        st.info("Não há dados suficientes para calcular yield com os filtros atuais.")
    else:
        fig_yield = go.Figure()
        fig_yield.add_bar(
            x=yield_data["fpy"],
            y=yield_data[yield_dimension].astype(str),
            orientation="h",
            text=yield_data["fpy"].map("{:.2%}".format),
            textposition="auto",
            customdata=yield_data[
                ["serials", "final_yield", "rework_rate", "scrap_rate"]
            ],
            hovertemplate=(
                "%{y}<br>"
                "FPY: %{x:.2%}<br>"
                "Seriais: %{customdata[0]:,}<br>"
                "Yield final: %{customdata[1]:.2%}<br>"
                "Rework: %{customdata[2]:.2%}<br>"
                "Scrap: %{customdata[3]:.2%}<extra></extra>"
            ),
        )
        fig_yield.update_layout(
            title="FPY por dimensão",
            xaxis_title="FPY",
            yaxis_title="",
            xaxis_tickformat=".0%",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig_yield, use_container_width=True)

        yield_display = yield_data.copy()
        for column in ["fpy", "final_yield", "rework_rate", "scrap_rate"]:
            yield_display[column] = yield_display[column].map("{:.2%}".format)
        st.dataframe(yield_display, use_container_width=True, hide_index=True)

    st.subheader("Prévia da base principal")
    st.dataframe(filtered_recordings.head(100), use_container_width=True)


with tab_failures:
    st.subheader("Falhas")

    failures = filtered_recordings[filtered_recordings["result"].eq("FAIL")].copy()

    col1, col2, col3 = st.columns(3)
    col1.metric("Tentativas filtradas", f"{len(filtered_recordings):,}")
    col2.metric("Falhas filtradas", f"{len(failures):,}")
    failure_rate = len(failures) / len(filtered_recordings) if len(filtered_recordings) else 0
    col3.metric("Taxa de falha", f"{failure_rate:.2%}")

    st.subheader("Pareto de defeitos")
    pareto_column = st.radio(
        "Agrupar Pareto por",
        ["failed_step", "error_code"],
        format_func={
            "failed_step": "Etapa com falha",
            "error_code": "Código de erro",
        }.get,
        horizontal=True,
    )

    pareto = build_pareto(failures, pareto_column)
    if pareto.empty:
        st.info("Não há falhas para os filtros atuais.")
    else:
        st.plotly_chart(
            plot_pareto(
                pareto,
                pareto_column,
                "Pareto de falhas",
            ),
            use_container_width=True,
        )
        st.dataframe(
            format_pareto_table(pareto),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("DPMO por etapa")
    dpmo_step_data = dpmo_by_step(filtered_recordings)
    if dpmo_step_data.empty:
        st.info("Não há dados suficientes para calcular DPMO por etapa.")
    else:
        fig_dpmo = go.Figure()
        fig_dpmo.add_bar(
            x=dpmo_step_data["dpmo"],
            y=dpmo_step_data["step"],
            orientation="h",
            text=dpmo_step_data["dpmo"].map("{:,.0f}".format),
            textposition="auto",
            customdata=dpmo_step_data[
                ["opportunities", "defects", "defect_rate"]
            ],
            hovertemplate=(
                "%{y}<br>"
                "DPMO: %{x:,.0f}<br>"
                "Oportunidades: %{customdata[0]:,}<br>"
                "Defeitos: %{customdata[1]:,}<br>"
                "Taxa: %{customdata[2]:.2%}<extra></extra>"
            ),
        )
        fig_dpmo.update_layout(
            title="DPMO por etapa",
            xaxis_title="DPMO",
            yaxis_title="",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig_dpmo, use_container_width=True)

        dpmo_display = dpmo_step_data.copy()
        dpmo_display["defect_rate"] = dpmo_display["defect_rate"].map(
            "{:.2%}".format
        )
        dpmo_display["dpmo"] = dpmo_display["dpmo"].map("{:,.0f}".format)
        st.dataframe(dpmo_display, use_container_width=True, hide_index=True)

    st.subheader("Jig x etapa")
    jig_step_rate = jig_step_matrix(filtered_recordings)
    if jig_step_rate.empty:
        st.info("Não há dados suficientes para montar a matriz Jig x etapa.")
    else:
        fig_jig_step = go.Figure(
            data=go.Heatmap(
                z=jig_step_rate.values * 100,
                x=jig_step_rate.columns.astype(str),
                y=jig_step_rate.index.astype(str),
                colorscale="Reds",
                colorbar={"title": "Taxa (%)"},
                hovertemplate=(
                    "Jig: %{y}<br>"
                    "Etapa: %{x}<br>"
                    "Taxa: %{z:.2f}%<extra></extra>"
                ),
            )
        )
        fig_jig_step.update_layout(
            title="Taxa de falha por Jig e etapa",
            xaxis_title="Etapa",
            yaxis_title="Jig",
            height=max(420, 26 * len(jig_step_rate.index)),
        )
        st.plotly_chart(fig_jig_step, use_container_width=True)

        st.dataframe(
            (jig_step_rate * 100).round(2),
            use_container_width=True,
        )

    st.subheader("Defeito principal: drm_keys / ERR_DRM")
    analysis_data = add_main_defect_flags(filtered_recordings)
    main_defect = analysis_data[analysis_data["is_main_defect"]]
    total_failures = analysis_data["is_fail"].sum()
    main_share_failures = (
        len(main_defect) / total_failures if total_failures else 0
    )
    main_share_attempts = (
        len(main_defect) / len(analysis_data) if len(analysis_data) else 0
    )

    col1, col2, col3 = st.columns(3)
    col1.metric("Ocorrências", f"{len(main_defect):,}")
    col2.metric("Participação nas falhas", f"{main_share_failures:.2%}")
    col3.metric("Participação nas tentativas", f"{main_share_attempts:.2%}")

    if main_defect.empty:
        st.info("O defeito principal não aparece nos filtros atuais.")
    else:
        start_defect = main_defect["timestamp"].min()
        end_defect = main_defect["timestamp"].max()
        st.caption(
            f"Janela filtrada do defeito: {start_defect} até {end_defect}"
        )

        dimension = st.selectbox(
            "Recortar defeito principal por",
            [
                "line",
                "station",
                "jig_id",
                "firmware_version",
                "model",
                "api_key",
            ],
            format_func={
                "line": "Linha",
                "station": "Estação",
                "jig_id": "Jig",
                "firmware_version": "Firmware",
                "model": "Modelo",
                "api_key": "API key",
            }.get,
        )

        summary = summarize_main_defect(analysis_data, dimension)
        summary = summary[summary["main_defects"].gt(0)].head(12)
        fig = go.Figure()
        fig.add_bar(
            x=summary["main_defect_rate"],
            y=summary[dimension].astype(str),
            orientation="h",
            text=summary["main_defect_rate"].map("{:.2%}".format),
            textposition="auto",
            customdata=summary[
                [
                    "total_attempts",
                    "total_failures",
                    "main_defects",
                    "ppm_main_defect",
                ]
            ],
            hovertemplate=(
                "%{y}<br>"
                "Taxa do defeito: %{x:.2%}<br>"
                "Tentativas: %{customdata[0]:,}<br>"
                "Falhas: %{customdata[1]:,}<br>"
                "Defeitos principais: %{customdata[2]:,}<br>"
                "PPM: %{customdata[3]:,.0f}<extra></extra>"
            ),
        )
        fig.update_layout(
            title="Taxa do defeito principal por dimensão",
            xaxis_title="Taxa do defeito principal",
            yaxis_title="",
            xaxis_tickformat=".0%",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig, use_container_width=True)

        display_summary = summary.copy()
        display_summary["failure_rate"] = display_summary["failure_rate"].map(
            "{:.2%}".format
        )
        display_summary["main_defect_rate"] = display_summary[
            "main_defect_rate"
        ].map("{:.2%}".format)
        display_summary["ppm_main_defect"] = display_summary[
            "ppm_main_defect"
        ].map("{:,.0f}".format)
        st.dataframe(display_summary, use_container_width=True, hide_index=True)

    st.subheader("Rework e scrap")
    disposition_data = disposition_summary(filtered_recordings)
    if disposition_data.empty:
        st.info("Não há dados de disposition para os filtros atuais.")
    else:
        fig_disposition = go.Figure()
        fig_disposition.add_bar(
            x=disposition_data["disposition"],
            y=disposition_data["attempts"],
            text=disposition_data["attempts"],
            textposition="outside",
        )
        fig_disposition.update_layout(
            title="Quebra por disposition",
            xaxis_title="Disposition",
            yaxis_title="Tentativas",
        )
        st.plotly_chart(fig_disposition, use_container_width=True)

    scrap_data = scrap_by_defect(filtered_recordings).head(20)
    if scrap_data.empty:
        st.info("Não há scrap nos filtros atuais.")
    else:
        fig_scrap = go.Figure()
        fig_scrap.add_bar(
            x=scrap_data["scrap_count"],
            y=(
                scrap_data["failed_step"].astype(str)
                + " | "
                + scrap_data["error_code"].astype(str)
                + " | "
                + scrap_data["line"].astype(str)
            ),
            orientation="h",
            text=scrap_data["scrap_count"],
            textposition="auto",
        )
        fig_scrap.update_layout(
            title="Top defeitos associados a scrap",
            xaxis_title="Scrap",
            yaxis_title="",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig_scrap, use_container_width=True)
        st.dataframe(scrap_data, use_container_width=True, hide_index=True)

    st.subheader("Acesso remoto: fw_download / ERR_AUTH")
    remote_data = remote_summary(filtered_recordings).head(15)
    if remote_data.empty:
        st.info("Não há dados para o recorte remoto nos filtros atuais.")
    else:
        fig_remote = go.Figure()
        fig_remote.add_bar(
            x=remote_data["remote_defect_rate"],
            y=(
                remote_data["line"].astype(str)
                + " | "
                + remote_data["api_key"].astype(str)
            ),
            orientation="h",
            text=remote_data["remote_defect_rate"].map("{:.2%}".format),
            textposition="auto",
            customdata=remote_data[["total_attempts", "remote_defects"]],
            hovertemplate=(
                "%{y}<br>"
                "Taxa remota: %{x:.2%}<br>"
                "Tentativas: %{customdata[0]:,}<br>"
                "Falhas remotas: %{customdata[1]:,}<extra></extra>"
            ),
        )
        fig_remote.update_layout(
            title="Taxa de falha remota por linha e API key",
            xaxis_title="Taxa de falha remota",
            yaxis_title="",
            xaxis_tickformat=".0%",
            yaxis={"autorange": "reversed"},
        )
        st.plotly_chart(fig_remote, use_container_width=True)
        st.dataframe(remote_data, use_container_width=True, hide_index=True)

    remote_time = remote_time_summary(filtered_recordings).head(30)
    if not remote_time.empty:
        st.caption("Maiores janelas de 15min com falha remota.")
        st.dataframe(remote_time, use_container_width=True, hide_index=True)

    st.subheader("Bluetooth e cabo")
    bt_data = bluetooth_summary(filtered_recordings).head(15)
    cable_data, zero_channel_rows = cable_summary(filtered_recordings)
    cable_top = cable_data.head(15) if not cable_data.empty else cable_data

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Bluetooth**")
        if bt_data.empty:
            st.info("Não há dados de Bluetooth nos filtros atuais.")
        else:
            st.dataframe(bt_data, use_container_width=True, hide_index=True)
    with col2:
        st.markdown("**Cabo / 0 canais**")
        if cable_top.empty:
            st.info("Não há dados de cabo nos filtros atuais.")
        else:
            st.dataframe(cable_top, use_container_width=True, hide_index=True)

    if not zero_channel_rows.empty:
        st.caption(f"Ocorrências com 0 canais: {len(zero_channel_rows):,}")
        zero_columns = [
            "timestamp",
            "line",
            "station",
            "jig_id",
            "model",
            "result",
            "failed_step",
            "error_code",
            "cable_channels_found",
            "disposition",
        ]
        st.dataframe(
            zero_channel_rows[zero_columns].head(100),
            use_container_width=True,
            hide_index=True,
        )

    st.subheader("Integridade: MAC e serial")
    integrity_summary, bad_mac_rows = integrity_checks(filtered_recordings)
    if integrity_summary.empty:
        st.info("Não há dados para checagem de integridade nos filtros atuais.")
    else:
        st.dataframe(integrity_summary, use_container_width=True, hide_index=True)

    if bad_mac_rows.empty:
        st.success("Nenhum MAC usado por mais de um serial nos filtros atuais.")
    else:
        st.warning("Existem MACs associados a mais de um serial nos filtros atuais.")
        st.dataframe(bad_mac_rows.head(200), use_container_width=True, hide_index=True)


with tab_time:
    st.subheader("Tempo e paradas")

    st.subheader("Falhas ao longo do tempo com paradas")
    time_data = failure_time_by_line(filtered_recordings)
    available_lines = sorted(time_data["line"].dropna().unique().tolist()) if not time_data.empty else []

    if not available_lines:
        st.info("Não há dados temporais para os filtros atuais.")
    else:
        selected_line_time = st.selectbox("Linha para série temporal", available_lines)
        line_time = time_data[time_data["line"].eq(selected_line_time)]
        line_stops = filtered_line_stops[filtered_line_stops["line"].eq(selected_line_time)]

        fig_time = go.Figure()
        fig_time.add_scatter(
            x=line_time["timestamp"],
            y=line_time["failure_rate"],
            mode="lines+markers",
            name="Taxa de falha",
            customdata=line_time[["total_attempts", "failures"]],
            hovertemplate=(
                "%{x}<br>"
                "Taxa de falha: %{y:.2%}<br>"
                "Tentativas: %{customdata[0]:,}<br>"
                "Falhas: %{customdata[1]:,}<extra></extra>"
            ),
        )

        for _, stop in line_stops.iterrows():
            fig_time.add_vrect(
                x0=stop["stop_start"],
                x1=stop["stop_end"],
                fillcolor="#D32F2F" if stop["category"] == "Unplanned" else "#90A4AE",
                opacity=0.18,
                line_width=0,
                annotation_text=str(stop["category"]),
                annotation_position="top left",
            )

        fig_time.update_layout(
            title=f"Taxa de falha por janela de 30min - {selected_line_time}",
            xaxis_title="Tempo",
            yaxis_title="Taxa de falha",
            yaxis_tickformat=".0%",
        )
        st.plotly_chart(fig_time, use_container_width=True)

    st.subheader("Tendência do defeito principal")
    main_time = main_defect_time(filtered_recordings)
    if main_time.empty:
        st.info("Não há dados do defeito principal para os filtros atuais.")
    else:
        fig_main_time = go.Figure()
        fig_main_time.add_scatter(
            x=main_time["timestamp"],
            y=main_time["main_defect_rate"],
            mode="lines+markers",
            name="Taxa por janela",
        )
        fig_main_time.add_scatter(
            x=main_time["timestamp"],
            y=main_time["main_defect_rate_ma3"],
            mode="lines",
            name="Média móvel de 3 janelas",
            line={"width": 3},
        )
        fig_main_time.update_layout(
            title="Taxa do defeito drm_keys + ERR_DRM por janela de 30min",
            xaxis_title="Tempo",
            yaxis_title="Taxa do defeito principal",
            yaxis_tickformat=".0%",
        )
        st.plotly_chart(fig_main_time, use_container_width=True)
        st.dataframe(main_time, use_container_width=True, hide_index=True)

    st.subheader("Downtime e disponibilidade")
    downtime_data = downtime_by_reason(filtered_line_stops)
    availability_data = availability_by_line(filtered_recordings, filtered_line_stops)

    col1, col2 = st.columns(2)
    with col1:
        if downtime_data.empty:
            st.info("Não há paradas nos filtros atuais.")
        else:
            fig_downtime = go.Figure()
            fig_downtime.add_bar(
                x=downtime_data["downtime_min"],
                y=(
                    downtime_data["line"].astype(str)
                    + " | "
                    + downtime_data["category"].astype(str)
                    + " | "
                    + downtime_data["reason"].astype(str)
                ),
                orientation="h",
                text=downtime_data["downtime_min"].map("{:.1f} min".format),
                textposition="auto",
            )
            fig_downtime.update_layout(
                title="Downtime por linha/categoria/motivo",
                xaxis_title="Minutos",
                yaxis_title="",
                yaxis={"autorange": "reversed"},
            )
            st.plotly_chart(fig_downtime, use_container_width=True)
    with col2:
        if availability_data.empty:
            st.info("Não há dados para disponibilidade.")
        else:
            fig_availability = go.Figure()
            fig_availability.add_bar(
                x=availability_data["line"],
                y=availability_data["availability"],
                text=availability_data["availability"].map("{:.2%}".format),
                textposition="auto",
            )
            fig_availability.update_layout(
                title="Disponibilidade por linha",
                xaxis_title="Linha",
                yaxis_title="Disponibilidade",
                yaxis_tickformat=".0%",
            )
            st.plotly_chart(fig_availability, use_container_width=True)

    if not downtime_data.empty:
        st.dataframe(downtime_data, use_container_width=True, hide_index=True)
    if not availability_data.empty:
        availability_display = availability_data.copy()
        for column in ["availability", "downtime_rate"]:
            availability_display[column] = availability_display[column].map("{:.2%}".format)
        st.dataframe(availability_display, use_container_width=True, hide_index=True)

    st.subheader("Cycle time")
    cycle_data = cycle_time_summary(filtered_recordings)
    if cycle_data.empty:
        st.info("Não há dados de cycle time para os filtros atuais.")
    else:
        bottleneck = cycle_data.iloc[0]
        st.metric("Gargalo por mediana", f"{bottleneck['step']} ({bottleneck['median_s']:.2f}s)")

        col1, col2 = st.columns(2)
        with col1:
            fig_cycle = go.Figure()
            fig_cycle.add_bar(
                x=cycle_data["median_s"],
                y=cycle_data["step"],
                orientation="h",
                text=cycle_data["median_s"].map("{:.2f}s".format),
                textposition="auto",
            )
            fig_cycle.update_layout(
                title="Mediana de cycle time por etapa",
                xaxis_title="Segundos",
                yaxis_title="",
                yaxis={"autorange": "reversed"},
            )
            st.plotly_chart(fig_cycle, use_container_width=True)
        with col2:
            outlier_data = cycle_data.sort_values("outliers", ascending=False)
            fig_outliers = go.Figure()
            fig_outliers.add_bar(
                x=outlier_data["outliers"],
                y=outlier_data["step"],
                orientation="h",
                text=outlier_data["outliers"],
                textposition="auto",
            )
            fig_outliers.update_layout(
                title="Outliers de cycle time por etapa",
                xaxis_title="Outliers",
                yaxis_title="",
                yaxis={"autorange": "reversed"},
            )
            st.plotly_chart(fig_outliers, use_container_width=True)

        st.dataframe(cycle_data.round(2), use_container_width=True, hide_index=True)


with tab_audit:
    st.subheader("Auditoria")

    audit_columns = [
        "timestamp",
        "date",
        "time",
        "shift",
        "line",
        "station",
        "jig_id",
        "operator",
        "model",
        "sku",
        "wifi_band",
        "has_bluetooth",
        "has_cable",
        "firmware_version",
        "serial_number",
        "mac_address",
        "api_key",
        "attempt",
        "total_cycle_s",
        "result",
        "failed_step",
        "error_code",
        "disposition",
    ]
    audit_columns = [
        column for column in audit_columns if column in filtered_recordings.columns
    ]
    audit_data = filtered_recordings[audit_columns].sort_values("timestamp")

    st.caption(f"{len(audit_data):,} registros encontrados com os filtros atuais.")
    st.dataframe(audit_data, use_container_width=True, hide_index=True)

    csv_data = audit_data.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Baixar auditoria CSV",
        data=csv_data,
        file_name="auditoria_filtrada.csv",
        mime="text/csv",
        disabled=audit_data.empty,
    )

    st.subheader("Relatório exportável")
    report_pareto = build_pareto(
        filtered_recordings[filtered_recordings["result"].eq("FAIL")],
        "error_code",
    )
    report_main_defect = add_main_defect_flags(filtered_recordings)
    report_main_defect = report_main_defect[report_main_defect["is_main_defect"]]
    report_availability = availability_by_line(filtered_recordings, filtered_line_stops)
    report_cycle = cycle_time_summary(filtered_recordings)
    report_scrap = scrap_by_defect(filtered_recordings)
    report_remote = remote_summary(filtered_recordings)
    report_bt = bluetooth_summary(filtered_recordings)
    report_cable, _ = cable_summary(filtered_recordings)
    report_integrity_summary, report_bad_macs = integrity_checks(filtered_recordings)
    report_text = build_markdown_report(
        filtered_kpis,
        report_pareto,
        report_main_defect,
        report_availability,
        report_cycle,
        report_scrap,
        report_integrity_summary,
        report_remote,
        report_bt,
        report_cable,
        report_bad_macs,
    )

    st.download_button(
        "Baixar relatório Markdown",
        data=report_text.encode("utf-8"),
        file_name="relatorio_anomalias.md",
        mime="text/markdown",
    )


with tab_docs:
    st.subheader("BPMN e PDD")
    if BPMN_IMAGE.exists():
        st.image(str(BPMN_IMAGE), caption="BPMN as-is do processo")
    else:
        st.info("Adicione o arquivo BPMN-as-is.png na raiz do projeto.")

    st.subheader("PDD")
    if PDD_PATH.exists():
        st.markdown(PDD_PATH.read_text(encoding="utf-8"))
    else:
        st.info("Adicione o arquivo pdd-setupbox.md na raiz do projeto.")
