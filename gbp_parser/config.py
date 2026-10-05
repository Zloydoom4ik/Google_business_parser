"""Paths and database settings; the values come from .env in the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DB = {
    "host": "127.0.0.1",
    "port": os.environ["POSTGRES_PORT"],
    "dbname": os.environ["POSTGRES_DB"],
    "user": os.environ["POSTGRES_USER"],
    "password": os.environ["POSTGRES_PASSWORD"],
}
DATA_DIR = ROOT / "data"
PLACES_FILE = ROOT / "places.json"
SCHEMA_FILE = ROOT / "schema.sql"
