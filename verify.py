import os
import sqlite3
from pathlib import Path
from beenative.settings import settings
from beenative.db.repository import db_url as async_url


def verify():
    print("--- 📂 PATH VERIFICATION ---")
    project_root = Path(__file__).resolve().parent
    print(f"Project Root: {project_root}")

    # 1. Check Settings
    db_path = settings.db_name
    print(f"Settings.db_name (Absolute): {db_path}")

    # 2. Check Async URL (What Flet uses)
    print(f"Async DB URL: {async_url}")

    # 3. Physical File Check
    if os.path.exists(db_path):
        size = os.path.getsize(db_path) / 1024
        print(f"✅ Database file found at: {db_path} ({size:.2f} KB)")

        # 4. Content Check
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='plants'")
            table_exists = cursor.fetchone()

            if table_exists:
                cursor.execute("SELECT COUNT(*) FROM plants")
                count = cursor.fetchone()[0]
                print(f"✅ Table 'plants' exists. Row count: {count}")

                if count > 0:
                    cursor.execute("SELECT scientific_name FROM plants LIMIT 3")
                    samples = cursor.fetchall()
                    print(f"   Sample data: {[s[0] for s in samples]}")
                else:
                    print("⚠️ Table 'plants' is EMPTY. Did you run the scraper/prep_db?")
            else:
                print("❌ Table 'plants' DOES NOT EXIST in this file.")
            conn.close()
        except Exception as e:
            print(f"❌ Error reading database: {e}")
    else:
        print(f"❌ NO DATABASE FILE FOUND at {db_path}")
        print("   Current working directory:", os.getcwd())


if __name__ == "__main__":
    verify()
