import json

import sqlalchemy as sa
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class JsonList(sa.types.TypeDecorator):
    """
    Enables JSON storage of lists in SQLite.
    Returns a list on the Python side, but saves as a string in the DB.
    """

    impl = sa.Unicode
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            return json.dumps(value)
        return "[]"

    def process_result_value(self, value, dialect):
        # This is the safety check that prevents the 'char 0' error
        if value is None or value.strip() == "":
            return []
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            # If the database has bad data like "Perennial" (no brackets),
            # treat it as a single-item list
            return [value]
