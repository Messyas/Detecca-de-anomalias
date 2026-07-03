from __future__ import annotations

# Este arquivo executa a entrada inicial do monitor.
# Ele le logs, atualiza o estado acumulado e salva um resumo da ingestao.

import argparse
import sys
from pathlib import Path

try:
    from .baseline import build_historical_baseline
    from .ingestion import (
        LogReadError,
        build_ingestion_summary,
        combine_line_stops,
        combine_recordings,
        load_batches_in_order,
        load_config,
        read_log_file,
    )
    from .outputs import (
        build_hitl_queue,
        build_periodic_report,
        write_audit_log,
        write_periodic_report,
    )
    from .rules import run_main_rules
    from .state import (
        add_audit_event,
        load_state,
        register_emitted_alert,
        register_processed_batch,
        save_state,
        was_file_processed,
    )
except ImportError:
    from baseline import build_historical_baseline
    from ingestion import (
        LogReadError,
        build_ingestion_summary,
        combine_line_stops,
        combine_recordings,
        load_batches_in_order,
        load_config,
        read_log_file,
    )
    from outputs import (
        build_hitl_queue,
        build_periodic_report,
        write_audit_log,
        write_periodic_report,
    )
    from rules import run_main_rules
    from state import (
        add_audit_event,
        load_state,
        register_emitted_alert,
        register_processed_batch,
        save_state,
        was_file_processed,
    )


# Le os argumentos informados na linha de comando.
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Executa a etapa de ingestao do monitor de anomalias."
    )
    parser.add_argument(
        "--input",
        default="Logs",
        help="Pasta com arquivos de log .xlsx ou .csv.",
    )
    parser.add_argument(
        "--output",
        default="Output",
        help="Pasta onde as saidas da ingestao serao salvas.",
    )
    parser.add_argument(
        "--config",
        default="Monitor/config.json",
        help="Caminho do arquivo de configuracao do monitor.",
    )
    parser.add_argument(
        "--baseline",
        default="Data/recording_test_setupbox.xlsx",
        help="Arquivo historico usado para calcular o baseline.",
    )
    return parser.parse_args()


# Executa a ingestao e atualiza o estado acumulado.
def main() -> int:
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    config_path = Path(args.config)
    baseline_path = Path(args.baseline)

    try:
        config = load_config(config_path)
        batches = load_batches_in_order(input_dir, config)
    except (OSError, LogReadError) as error:
        print(f"Erro de entrada: {error}", file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    state_file = config.get("output", {}).get("state_file", "monitor_state.json")
    state_path = output_dir / state_file
    state = load_state(state_path)

    try:
        baseline_batch = read_log_file(baseline_path, config)
    except (OSError, LogReadError) as error:
        print(f"Erro no baseline: {error}", file=sys.stderr)
        return 2

    baseline_summary = build_historical_baseline(baseline_batch.recordings, config)
    baseline_file = config.get("output", {}).get(
        "baseline_file",
        "baseline_summary.csv",
    )
    baseline_summary_path = output_dir / baseline_file
    baseline_summary.to_csv(baseline_summary_path, index=False)

    add_audit_event(
        state,
        event_type="run_started",
        details={"input_dir": str(input_dir), "files_found": len(batches)},
    )
    add_audit_event(
        state,
        event_type="baseline_generated",
        file=baseline_path.name,
        details={
            "baseline_rows": len(baseline_summary),
            "output": str(baseline_summary_path),
        },
    )

    processed_batches = []
    skipped_files = []
    for batch in batches:
        if was_file_processed(state, batch.path.name):
            skipped_files.append(batch.path.name)
            add_audit_event(
                state,
                event_type="file_skipped",
                file=batch.path.name,
                details={"reason": "already_processed"},
            )
            continue

        register_processed_batch(state, batch)
        processed_batches.append(batch)

    processed_recordings = combine_recordings(processed_batches)
    processed_line_stops = combine_line_stops(processed_batches)
    alerts, outliers = run_main_rules(
        processed_recordings,
        processed_line_stops,
        baseline_summary,
        state,
        config,
    )

    alerts_file = config.get("output", {}).get("alerts_file", "alerts.csv")
    outliers_file = config.get("output", {}).get(
        "outliers_file",
        "outliers_ignored.csv",
    )
    alerts_path = output_dir / alerts_file
    outliers_path = output_dir / outliers_file
    alerts.to_csv(alerts_path, index=False)
    outliers.to_csv(outliers_path, index=False)

    for alert_id in alerts["alert_id"].dropna().tolist():
        register_emitted_alert(state, alert_id)

    summary = build_ingestion_summary(processed_batches)
    summary_path = output_dir / "ingestion_summary.csv"
    summary.to_csv(summary_path, index=False)

    hitl_file = config.get("output", {}).get("hitl_queue_file", "hitl_queue.csv")
    audit_file = config.get("output", {}).get("audit_file", "audit_log.jsonl")
    report_file = config.get("output", {}).get(
        "periodic_report_file",
        "periodic_report.md",
    )
    hitl_path = output_dir / hitl_file
    audit_path = output_dir / audit_file
    report_path = output_dir / report_file

    hitl_queue = build_hitl_queue(alerts)
    hitl_queue.to_csv(hitl_path, index=False)

    report_text = build_periodic_report(
        alerts=alerts,
        outliers=outliers,
        hitl_queue=hitl_queue,
        baseline=baseline_summary,
        ingestion_summary=summary,
        config=config,
        output_paths={
            "baseline": baseline_summary_path,
            "alerts": alerts_path,
            "outliers": outliers_path,
            "hitl_queue": hitl_path,
            "audit_log": audit_path,
            "ingestion_summary": summary_path,
        },
    )
    write_periodic_report(report_text, report_path)

    add_audit_event(
        state,
        event_type="rules_finished",
        details={
            "alerts": len(alerts),
            "outliers_ignored": len(outliers),
            "alerts_output": str(alerts_path),
            "outliers_output": str(outliers_path),
        },
    )
    add_audit_event(
        state,
        event_type="outputs_generated",
        details={
            "hitl_queue": str(hitl_path),
            "audit_log": str(audit_path),
            "periodic_report": str(report_path),
        },
    )
    add_audit_event(
        state,
        event_type="run_finished",
        details={
            "files_processed": len(processed_batches),
            "files_skipped": len(skipped_files),
            "alerts": len(alerts),
            "outliers_ignored": len(outliers),
        },
    )
    save_state(state, state_path)
    write_audit_log(state, audit_path)

    if not batches:
        print("Nenhum arquivo de log encontrado.")
        print(f"Baseline salvo em: {baseline_summary_path}")
        print(f"Alertas salvos em: {alerts_path}")
        print(f"Outliers salvos em: {outliers_path}")
        print(f"Fila HITL salva em: {hitl_path}")
        print(f"Auditoria salva em: {audit_path}")
        print(f"Relatorio periodico salvo em: {report_path}")
        print(f"Resumo salvo em: {summary_path}")
        print(f"Estado salvo em: {state_path}")
        return 0

    if not processed_batches:
        print("Nenhum arquivo novo para processar.")
        print(f"Arquivos ja processados: {len(skipped_files)}")
        print(f"Baseline salvo em: {baseline_summary_path}")
        print(f"Alertas salvos em: {alerts_path}")
        print(f"Outliers salvos em: {outliers_path}")
        print(f"Fila HITL salva em: {hitl_path}")
        print(f"Auditoria salva em: {audit_path}")
        print(f"Relatorio periodico salvo em: {report_path}")
        print(f"Resumo salvo em: {summary_path}")
        print(f"Estado salvo em: {state_path}")
        return 0

    print("Arquivos de log processados em ordem cronologica:")
    for row in summary.itertuples(index=False):
        print(
            f"{row.order}. {row.file} | "
            f"{row.start_time} -> {row.end_time} | "
            f"{row.recording_rows} linhas"
        )

    if skipped_files:
        print(f"Arquivos ignorados por ja estarem no estado: {len(skipped_files)}")

    print(f"Baseline salvo em: {baseline_summary_path}")
    print(f"Alertas salvos em: {alerts_path} ({len(alerts)} alertas)")
    print(f"Outliers salvos em: {outliers_path} ({len(outliers)} ignorados)")
    print(f"Fila HITL salva em: {hitl_path} ({len(hitl_queue)} pendentes)")
    print(f"Auditoria salva em: {audit_path}")
    print(f"Relatorio periodico salvo em: {report_path}")
    print(f"Resumo salvo em: {summary_path}")
    print(f"Estado salvo em: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
