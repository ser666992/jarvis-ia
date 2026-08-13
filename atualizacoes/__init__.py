from atualizacoes.updater import aplicar_atualizacao, check_for_updates, iniciar, is_git_repo
from atualizacoes.version import VERSION
from atualizacoes.safe_updater import apply_validated, last_report, validate_candidate, working_tree_status

__all__ = [
    "VERSION", "check_for_updates", "aplicar_atualizacao", "iniciar", "is_git_repo",
    "status", "validate_candidate", "apply_validated", "last_report", "working_tree_status",
]


def status() -> dict:
    report = check_for_updates()
    return {
        "disponivel": True,
        "motivo": f"v{VERSION} -- {report['motivo']}",
        "detalhes": report,
    }
