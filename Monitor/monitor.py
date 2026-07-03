from __future__ import annotations

# Este arquivo executa a entrada inicial do monitor.
# Ele le logs, atualiza o estado acumulado e salva um resumo da ingestao.

import argparse
import sys
from pathlib import Path

try:
    from .ingestion import (
        LogReadError,
        build_ingestion_summary,
        load_batches_in_order,
        load_config,
    )
    from .state import (
        add_audit_event,
        load_state,
        register_processed_batch,
        save_state,
        was_file_processed,
    )
except ImportError:
    from ingestion import (
        LogReadError,
        build_ingestion_summary,
        load_batches_in_order,
        load_config,
    )
    from state import (
        add_audit_event,
        load_state,
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
    return parser.parse_args()


# Executa a ingestao e atualiza o estado acumulado.
def main() -> int:
    args = parse_args()
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    config_path = Path(args.config)

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

    add_audit_event(
        state,
        event_type="run_started",
        details={"input_dir": str(input_dir), "files_found": len(batches)},
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

    add_audit_event(
        state,
        event_type="run_finished",
        details={
            "files_processed": len(processed_batches),
            "files_skipped": len(skipped_files),
        },
    )
    save_state(state, state_path)

    summary = build_ingestion_summary(processed_batches)
    summary_path = output_dir / "ingestion_summary.csv"
    summary.to_csv(summary_path, index=False)

    if not batches:
        print("Nenhum arquivo de log encontrado.")
        print(f"Resumo salvo em: {summary_path}")
        print(f"Estado salvo em: {state_path}")
        return 0

    if not processed_batches:
        print("Nenhum arquivo novo para processar.")
        print(f"Arquivos ja processados: {len(skipped_files)}")
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

    print(f"Resumo salvo em: {summary_path}")
    print(f"Estado salvo em: {state_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
