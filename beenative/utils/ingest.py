import os
import json
import sqlite3

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

        # 1. High speed write to staging
        processed_df.write_database(
            table_name=staging_table, connection=self.db_uri, engine="adbc", if_table_exists="replace"
        )

        # 2. Get columns safely
        cols = [f'"{c}"' for c in processed_df.columns]
        col_list = ", ".join(cols)

        # 3. Use the Atomic Delete-and-Insert Pattern
        # This is logically equivalent to UPSERT but much more stable for large schemas
        sql_commands = [
            # Remove existing rows that match our new data
            f"DELETE FROM {table_name} WHERE scientific_name IN (SELECT scientific_name FROM {staging_table})",
            # Insert the new data
            f"INSERT INTO {table_name} ({col_list}) SELECT {col_list} FROM {staging_table}",
            # Cleanup
            f"DROP TABLE {staging_table}",
        ]

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            for cmd in sql_commands:
                cursor.execute(cmd)
            conn.commit()

        print(f"Successfully synchronized {len(df)} records.")
        print(f"File size: {os.path.getsize(self.db_path) / 1024:.2f} KB")

    def query(self, sql_query, params=()):
        """Returns a Polars DF from any SQL query"""
        with sqlite3.connect(self.db_path) as conn:
            return pl.read_database(sql_query, conn, tuple(params))
