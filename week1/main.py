from pathlib import Path # This import to help us handle file paths in a platform-independent way
import sys 
from src.ingestor import ingest_all_mhtml
from src.processor import process_all_html
from src.loader import load_all_jsons
from src.profiler import run_data_profile
import logging

SOURCE_DIR = Path("data/0_source")
BRONZE_DIR = Path("data/1_bronze")
SILVER_DIR = Path("data/2_silver")
GOLD_DIR = Path("data/3_gold")
DB_NAME = "jobs.db"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s |%(levelname)s |%(message)s"
)

def run_profiler():
    db_path = GOLD_DIR/DB_NAME
    run_data_profile(db_path)

def run_gold():
    input_dir = SILVER_DIR
    output_dir = GOLD_DIR
    load_all_jsons(input_dir, output_dir)

def run_silver():
    input_dir = BRONZE_DIR
    output_dir = SILVER_DIR
    process_all_html(input_dir, output_dir)


def run_bronze():
    input_dir = SOURCE_DIR
    output_dir = BRONZE_DIR
    ingest_all_mhtml(input_dir, output_dir)
    
def main():

    if len(sys.argv) < 2:
        print("Usage: python main.py [ingest|process|load|profile|all]")
        return

    command = sys.argv[1]

    if command == "ingest":
        run_bronze()
    elif command == "process":
        run_silver()
    elif command == "load":
        run_gold()
    elif command == "profile":
        run_profiler()
    elif command == "all":
        run_bronze()
        run_silver()
        run_gold()
        run_profiler()
    else:
        print("Usage: python main.py [ingest|process|load|profile|all]")


if __name__ == "__main__":
    main()