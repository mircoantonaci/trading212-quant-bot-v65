#!/usr/bin/env python3
"""
setup_github_cloud.py — Configurazione Automatica Repository GitHub & Cloud H24 (GitHub Actions)
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path("/Users/antonacim/.gemini/antigravity/scratch/trading-arena-50e")
SIBLING_DIR = Path("/Users/antonacim/Local Sites/trading212-quant-bot-v65")
CREDS_FILE = PROJECT_DIR / "t212_credentials.json"
REPO_NAME = "mircoantonaci/trading212-quant-bot-v65"


def run_cmd(cmd: list[str], cwd: Path = PROJECT_DIR, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=str(cwd),
        input=input_text,
        text=True,
        capture_output=True,
        check=check,
    )


def main() -> None:
    print(f"🚀 Inizializzazione progetto GitHub: {REPO_NAME}")

    # 1. Verifica se la repo esiste già su GitHub, altrimenti creala privata
    view_res = run_cmd(["gh", "repo", "view", REPO_NAME], check=False)
    if view_res.returncode != 0:
        print("📦 Creazione nuovo repository privato su GitHub...")
        create_res = run_cmd(
            [
                "gh",
                "repo",
                "create",
                REPO_NAME,
                "--private",
                "--description",
                "Trading 212 Autonomous Quant Bot V6.5 Institutional Zero-Latency (12 Shields, 4x25 EUR, 730 LIFO, Cloud H24)",
                "--source",
                str(PROJECT_DIR),
                "--remote",
                "origin",
                "--push",
            ],
            check=False,
        )
        if create_res.returncode != 0:
            print("Errore creazione repo:", create_res.stderr)
            sys.exit(1)
        print("✅ Repository creato e codice pushato su GitHub!")
    else:
        print("ℹ️ Repository già esistente su GitHub, sincronizzazione remote e push...")
        run_cmd(["git", "remote", "remove", "origin"], check=False)
        run_cmd(["git", "remote", "add", "origin", f"https://github.com/{REPO_NAME}.git"], check=False)
        push_res = run_cmd(["git", "push", "-u", "origin", "main", "--force"], check=False)
        if push_res.returncode != 0:
            print("Errore push:", push_res.stderr)
            sys.exit(1)
        print("✅ Codice aggiornato su GitHub!")

    # 2. Configura i GitHub Encrypted Secrets per l'esecuzione Cloud H24
    creds = json.loads(CREDS_FILE.read_text(encoding="utf-8"))
    secrets = {
        "T212_API_KEY": creds["api_key"],
        "T212_API_SECRET": creds["api_secret"],
        "T212_MODE": creds.get("mode", "demo"),
    }
    for s_name, s_val in secrets.items():
        res = run_cmd(["gh", "secret", "set", s_name, "--repo", REPO_NAME], input_text=s_val, check=False)
        if res.returncode == 0:
            print(f"🔐 Secret cifrato configurato su GitHub Actions: {s_name}")
        else:
            print(f"⚠️ Errore configurazione secret {s_name}: {res.stderr}")

    # 3. Avvia subito un ciclo di test del workflow Cloud H24 su GitHub Actions
    wf_res = run_cmd(
        ["gh", "workflow", "run", "t212_cloud_h24.yml", "--repo", REPO_NAME, "-f", "cycles=2"],
        check=False,
    )
    if wf_res.returncode == 0:
        print("☁️ Workflow Cloud H24 ('t212_cloud_h24.yml') attivato e lanciato su GitHub Actions!")
    else:
        print(f"ℹ️ Nota avvio workflow: {wf_res.stderr.strip()}")

    # 4. Crea anche la cartella gemella fuori da gastronomia (/Users/antonacim/Local Sites/trading212-quant-bot-v65)
    try:
        if SIBLING_DIR.exists():
            shutil.rmtree(SIBLING_DIR)
        shutil.copytree(PROJECT_DIR, SIBLING_DIR)
        print(f"📂 Progetto ad-hoc copiato fuori da gastronomia in: {SIBLING_DIR}")
    except Exception as exc:
        print(f"ℹ️ Nota copia cartella locale: {exc}")


if __name__ == "__main__":
    main()
