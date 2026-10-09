import json
import sqlite3
from pathlib import Path

import polars as pl

from beenative.settings import settings


class BeeNativeDB:
    def __init__(self):
        self.db_path = settings.initial_db_path
        self.db_uri = settings.sync_init_database_url

    def _prepare_for_sqlite(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Ensures Polars types match SQLAlchemy/SQLite expectations:
        1. Lists -> JSON Strings (for columns like 'plant_categories' or 'sunlight')
        2. Booleans -> Integers (0/1)
        3. Structs/Objects -> JSON Strings
        """
        # Identify columns by their Polars DataType
        list_cols = [col for col, dtype in df.schema.items() if isinstance(dtype, pl.List)]
        bool_cols = [col for col, dtype in df.schema.items() if dtype == pl.Boolean]
        struct_cols = [col for col, dtype in df.schema.items() if isinstance(dtype, pl.Struct)]

        # Apply transformations
        return df.with_columns(
            [
                # 1. Convert Lists to JSON strings
                pl.col(list_cols).map_elements(
                    lambda x: json.dumps(list(x)) if x is not None else "[]", return_dtype=pl.Utf8
                ),
                # 2. Convert Structs to JSON strings (if you have complex nested data)
                pl.col(struct_cols).map_elements(
                    lambda x: json.dumps(x) if x is not None else "{}", return_dtype=pl.Utf8
                ),
                # 3. Explicitly cast Booleans to Integers for SQLite
                pl.col(bool_cols).cast(pl.Int32),
            ]
        )

    def save_dataframe(self, df: pl.DataFrame, table_name: str = "plants"):
        processed_df = self._prepare_for_sqlite(df)
        staging_table = f"{table_name}_staging"

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # 1. Clean up any lingering staging table from previous failed runs
            cursor.execute(f"DROP TABLE IF EXISTS {staging_table}")

            # 2. Dynamically create a lightweight staging table
            cols = [f'"{c}"' for c in processed_df.columns]
            col_defs = ", ".join(cols)
            cursor.execute(f"CREATE TABLE {staging_table} ({col_defs})")

            # 3. Extract native Python types using pure Polars and batch insert
            placeholders = ", ".join(["?"] * len(cols))
            cursor.executemany(
                f"INSERT INTO {staging_table} VALUES ({placeholders})",
                processed_df.rows()
            )

            # 4. Perform atomic UPSERT merge
            col_list = ", ".join(cols)
            cursor.execute(
                f"DELETE FROM {table_name} WHERE scientific_name IN (SELECT scientific_name FROM {staging_table})"
            )
            cursor.execute(
                f"INSERT INTO {table_name} ({col_list}) SELECT {col_list} FROM {staging_table}"
            )

            # 5. Cleanup
            cursor.execute(f"DROP TABLE {staging_table}")

            conn.commit()

        print(f"Successfully synchronized {len(df)} records.")
        print(f"File size: {Path(self.db_path).stat().st_size / 1024:.2f} KB")

    def query(self, sql_query, params=()):
        """Returns a Polars DF from any SQL query"""
        with sqlite3.connect(self.db_path) as conn:
            if params:
                return pl.read_database(
                    sql_query,
                    connection=conn,
                    execute_options={"parameters": tuple(params)}
                )
            return pl.read_database(sql_query, connection=conn)
