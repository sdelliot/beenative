import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from models.plant import Plant


async def search_plants(
    session: AsyncSession, search_term: str = None, filters: dict = None, offset: int = 0, limit: int = 20
):
    # Start with a base select statement
    stmt = sa.select(Plant)

    # List to store our combined conditions
    conditions = []

    # 1. Broad Text Search (OR logic between columns)
    if search_term:
        search_pattern = f"%{search_term}%"

        # 1. Define the table-valued function for the JSON list
        # We name the output column "value" so we can reference it
        names_tab = sa.func.json_each(Plant.all_common_names).table_valued("value")

        # 2. Build the "EXISTS" subquery properly
        common_names_subquery = (
            sa.select(1).select_from(names_tab).where(names_tab.c.value.ilike(search_pattern)).exists()
        )

        # 3. Combine everything in the OR block
        conditions.append(
            sa.or_(
                Plant.scientific_name.ilike(search_pattern),
                Plant.ncsu_description.ilike(search_pattern),
                Plant.pm_about.ilike(search_pattern),
                Plant.vasc_identification.ilike(search_pattern),
                Plant.vasc_taxonomic_comments.ilike(search_pattern),
                common_names_subquery,
            )
        )

    # 2. Structured Filters (AND logic between different filters)
    if filters:
        for col_name, value in filters.items():
            if not value or not hasattr(Plant, col_name):
                continue

            column = getattr(Plant, col_name)

            # If the UI sends a list (e.g., ["Forbs", "Vines"])
            search_values = value if isinstance(value, list) else [value]

            if col_name in ["plant_categories", "flower_colors", "sunlight"]:
                for val in search_values:
                    # We add a separate condition for EACH selected category
                    # This enforces the "AND" relationship (Must have Forb AND must have Vine)
                    json_tab = sa.func.json_each(column).table_valued("value")
                    conditions.append(sa.select(1).select_from(json_tab).where(json_tab.c.value == val).exists())
            else:
                conditions.append(column == search_values[0])

    # Apply all gathered conditions to the statement
    if conditions:
        stmt = stmt.where(sa.and_(*conditions))

    # Order by common name and limit results
    stmt = stmt.order_by(Plant.pm_common_name).limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all()
