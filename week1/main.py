import sys
import logging

from src.ingestor import ingest_all_mhtml
from src.processor import process_all_html
from src.loader import load_all_jsons
from src.profiler import run_data_profile

# ── Logging configuration ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# ── Directory / path constants ────────────────────────────────────────────────
SOURCE_DIR = "data/0_source"
BRONZE_DIR = "data/1_bronze"
SILVER_DIR = "data/2_silver"
GOLD_DIR   = "data/3_gold"
DB_PATH    = "data/3_gold/jobs.db"


def cmd_ingest():
    ingest_all_mhtml(SOURCE_DIR, BRONZE_DIR)


def cmd_process():
    process_all_html(BRONZE_DIR, SILVER_DIR)


def cmd_load():
    load_all_jsons(SILVER_DIR, GOLD_DIR)


def cmd_profile():
    run_data_profile(DB_PATH)


def cmd_all():
    cmd_ingest()
    print()
    cmd_process()
    print()
    cmd_load()
    print()
    cmd_profile()


COMMANDS = {
    "ingest":  cmd_ingest,
    "process": cmd_process,
    "load":    cmd_load,
    "profile": cmd_profile,
    "all":     cmd_all,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: python main.py [ingest|process|load|profile|all]")
        sys.exit(0)

    COMMANDS[sys.argv[1]]()