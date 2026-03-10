# Database

This project uses [SQLAlchemy](https://www.sqlalchemy.org/) as its ORM (Object-Relational Mapper) and [Alembic](https://alembic.sqlalchemy.org/) for database migrations, providing full async/await support for high-performance database operations.

## Configuration

Database configuration is managed through Pydantic settings with the following environment variable:

- **DATABASE_URL**: Database connection string (default: `sqlite:///./test.db`)
  - SQLite: `sqlite:///./database.db` (local file) or `sqlite:///:memory:` (in-memory)
  - PostgreSQL: `postgresql://user:password@localhost:5432/dbname`

The database service automatically transforms the connection string for async operations:

- `sqlite` → `sqlite+aiosqlite` (async SQLite driver)
- `postgresql` → `postgresql+asyncpg` (async PostgreSQL driver)

## Database API

This project uses the modern SQLAlchemy 2.0 API with full async/await support:

- **Async Engine**: Provides asynchronous database connections
- **AsyncSession**: Manages database transactions asynchronously
- **Future-compatible**: Uses the `future=True` flag for forward compatibility

### Supported Databases

- **SQLite**: Perfect for development and testing, supports both file-based and in-memory databases
- **PostgreSQL**: Recommended for production, provides full relational database features

## Defining Models

Models are defined in the `beenative/models` directory and inherit from the declarative base.

### Basic Model Structure

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from beenative.models.base import Base

class User(Base):
    """User model."""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    bio: Mapped[str | None] = mapped_column(String(500))
```

### Column Types

SQLAlchemy provides a rich set of column types:

```python
import datetime
from typing import Any
from sqlalchemy import String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    is_published: Mapped[bool] = mapped_column(default=False)
    view_count: Mapped[int] = mapped_column(default=0)
    rating: Mapped[float | None]
    metadata: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime.datetime | None] = mapped_column(onupdate=func.now())
```

### Constraints and Indexes

```python
from sqlalchemy import String, UniqueConstraint, Index, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[float]
    category: Mapped[str] = mapped_column(String(100))

    __table_args__ = (
        # Composite unique constraint
        UniqueConstraint("name", "category", name="uq_product_name_category"),
        # Multi-column index for better query performance
        Index("idx_category_price", "category", "price"),
        # Check constraint
        CheckConstraint("price > 0", name="ck_product_price_positive"),
    )
```

## Relationships

SQLAlchemy provides powerful relationship patterns for connecting models.

### One-to-Many Relationship

```python
from typing import List
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

    # Relationship to books (one author has many books)
    books: Mapped[List["Book"]] = relationship(back_populates="author", cascade="all, delete-orphan")


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"))

    # Relationship to author (many books belong to one author)
    author: Mapped["Author"] = relationship(back_populates="books")
```

### Many-to-Many Relationship

```python
from typing import List
from sqlalchemy import Table, Column, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Association table for many-to-many relationship
student_course_association = Table(
    "student_courses",
    Base.metadata,
    Column("student_id", Integer, ForeignKey("students.id", ondelete="CASCADE")),
    Column("course_id", Integer, ForeignKey("courses.id", ondelete="CASCADE")),
)


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))

    # Many-to-many relationship to courses
    courses: Mapped[List["Course"]] = relationship(
        secondary=student_course_association,
        back_populates="students"
    )


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))

    # Many-to-many relationship to students
    students: Mapped[List["Student"]] = relationship(
        secondary=student_course_association,
        back_populates="courses"
    )
```

### Self-Referential Relationship

```python
from typing import List
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))

    # Self-referential relationship
    manager: Mapped["Employee | None"] = relationship(
        remote_side="Employee.id",
        back_populates="subordinates"
    )
    subordinates: Mapped[List["Employee"]] = relationship(back_populates="manager")
```

## Session Management

The database service provides async context managers for session management.

### Basic Session Usage

```python
from beenative.services.db import get_session

async def create_user(name: str, email: str):
    """Create a new user."""
    async with get_session() as session:
        user = User(name=name, email=email)
        session.add(user)
        await session.commit()
        await session.refresh(user)  # Get generated ID
        return user
```

### Querying Data

```python
from sqlalchemy import select

async def get_user_by_email(email: str):
    """Find a user by email."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()


async def get_all_users():
    """Get all users."""
    async with get_session() as session:
        result = await session.execute(select(User))
        return result.scalars().all()


async def get_users_by_name(name: str):
    """Find users by name pattern."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.name.like(f"%{name}%"))
        )
        return result.scalars().all()
```

### Updating Data

```python
async def update_user_email(user_id: int, new_email: str):
    """Update a user's email."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()
        user.email = new_email
        await session.commit()
        return user
```

### Deleting Data

```python
async def delete_user(user_id: int):
    """Delete a user."""
    async with get_session() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one()
        await session.delete(user)
        await session.commit()
```

### Transaction Management

```python
async def transfer_credits(from_user_id: int, to_user_id: int, amount: int):
    """Transfer credits between users with transaction safety."""
    async with get_session() as session:
        try:
            # Get both users
            from_user = (await session.execute(
                select(User).where(User.id == from_user_id)
            )).scalar_one()

            to_user = (await session.execute(
                select(User).where(User.id == to_user_id)
            )).scalar_one()

            # Perform transfer
            if from_user.credits < amount:
                raise ValueError("Insufficient credits")

            from_user.credits -= amount
            to_user.credits += amount

            await session.commit()

        except Exception:
            await session.rollback()
            raise
```

## FastAPI Integration

The `get_session_depends` function integrates seamlessly with FastAPI's dependency injection system.

### Using Database Sessions in Endpoints

```python
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from beenative.services.db import get_session_depends

@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_session_depends)
):
    """Get a user by ID."""
    result = await session.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.post("/users")
async def create_user(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_session_depends)
):
    """Create a new user."""
    user = User(**user_data.dict())
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
```

### Testing with Database Fixtures

The test suite provides database fixtures that override the dependency:

```python
def test_create_user(fastapi_client):
    """Test creating a user via API."""
    response = fastapi_client.post(
        "/users",
        json={"name": "Test User", "email": "test@example.com"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test User"
```

See [Testing Documentation](./testing.md#testing-database-operations) for more details on testing with databases.

## Migrations with Alembic

Alembic manages database schema changes through migration scripts, allowing you to version and track database structure over time.

### Creating Migrations

Alembic automatically detects changes in your models and generates migration scripts:

```bash
# Create a new migration
make create_migration MESSAGE="add user table"

# This creates a file like: db/versions/abc123_add_user_table.py
```

The migration generation process:

1. Creates a temporary SQLite database
2. Applies all existing migrations to it
3. Compares the current models with the migrated database schema
4. Generates a migration script with the differences
5. Automatically formats the generated script with ruff

### Migration Structure

Generated migrations contain `upgrade()` and `downgrade()` functions:

```python
"""add user table

Revision ID: abc123
Revises: xyz789
Create Date: 2024-01-15 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'abc123'
down_revision = 'xyz789'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table('users')
```

### Running Migrations

```bash
# Apply all pending migrations
make run_migrations

# Equivalent to:
alembic upgrade head

# Downgrade one migration
alembic downgrade -1

# Downgrade to a specific revision
alembic downgrade abc123

# View migration history
alembic history

# Show current migration version
alembic current
```

### Checking for Ungenerated Migrations

Before creating a new migration, check if there are pending model changes:

```bash
# Check if models have changed since last migration
make check_ungenerated_migrations

# Equivalent to:
alembic check
```

This command will:

- Exit with code 0 if no changes are detected
- Exit with code 1 if there are ungenerated changes
- Useful in CI/CD to ensure migrations are created for all model changes

### Migration Best Practices

1. **Descriptive messages**: Use clear, concise migration messages

   ```bash
   make create_migration MESSAGE="add user email verification fields"
   ```

2. **Small, focused migrations**: Each migration should address one logical change

   ```bash
   # Good - separate migrations
   make create_migration MESSAGE="add users table"
   make create_migration MESSAGE="add user indexes"

   # Bad - one large migration
   make create_migration MESSAGE="add users and products and orders"
   ```

3. **Test migrations**: Always test both upgrade and downgrade

   ```bash
   # Test upgrade
   make run_migrations

   # Test downgrade
   alembic downgrade -1

   # Re-upgrade
   make run_migrations
   ```

4. **Review generated migrations**: Always review auto-generated migrations before committing
   - Check for unintended changes
   - Add data migrations if needed
   - Verify indexes and constraints

5. **Data migrations**: For complex data transformations, add custom logic

   ```python
   def upgrade() -> None:
       # Schema change
       op.add_column('users', sa.Column('full_name', sa.String(200)))

       # Data migration
       connection = op.get_bind()
       connection.execute(
           sa.text("UPDATE users SET full_name = name WHERE full_name IS NULL")
       )
   ```

### Database Reset and Cleanup

```bash
# Clear the database (removes SQLite file)
make clear_db

# Clear and re-run all migrations
make reset_db
```

## Common CRUD Patterns

### Create

```python
async def create_record(data: dict):
    """Create a new record."""
    async with get_session() as session:
        record = MyModel(**data)
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record
```

### Read

```python
from sqlalchemy import select

async def get_record_by_id(record_id: int):
    """Get a single record by ID."""
    async with get_session() as session:
        result = await session.execute(
            select(MyModel).where(MyModel.id == record_id)
        )
        return result.scalar_one_or_none()


async def get_all_records(skip: int = 0, limit: int = 100):
    """Get paginated records."""
    async with get_session() as session:
        result = await session.execute(
            select(MyModel).offset(skip).limit(limit)
        )
        return result.scalars().all()


async def get_filtered_records(status: str):
    """Get records with filtering."""
    async with get_session() as session:
        result = await session.execute(
            select(MyModel).where(MyModel.status == status)
        )
        return result.scalars().all()
```

### Update

```python
async def update_record(record_id: int, updates: dict):
    """Update a record."""
    async with get_session() as session:
        result = await session.execute(
            select(MyModel).where(MyModel.id == record_id)
        )
        record = result.scalar_one()

        for key, value in updates.items():
            setattr(record, key, value)

        await session.commit()
        await session.refresh(record)
        return record
```

### Delete

```python
async def delete_record(record_id: int):
    """Delete a record."""
    async with get_session() as session:
        result = await session.execute(
            select(MyModel).where(MyModel.id == record_id)
        )
        record = result.scalar_one()
        await session.delete(record)
        await session.commit()
```

## Testing Database Operations

The test suite provides fixtures for database testing with isolated, in-memory databases.

### Using the db_session Fixture

```python
import pytest
from sqlalchemy import select

@pytest.mark.asyncio
async def test_create_user(db_session):
    """Test creating a user."""
    user = User(name="Test User", email="test@example.com")
    db_session.add(user)
    await db_session.commit()

    # Verify creation
    result = await db_session.execute(
        select(User).where(User.email == "test@example.com")
    )
    saved_user = result.scalar_one()
    assert saved_user.name == "Test User"
```

See [Testing Documentation](./testing.md) for comprehensive testing patterns.

## Best Practices

1. **Always use async/await**: This project uses async SQLAlchemy exclusively

   ```python
   # Good
   async with get_session() as session:
       result = await session.execute(query)

   # Bad - will not work
   with get_session() as session:
       result = session.execute(query)
   ```

2. **Use context managers for sessions**: Ensures proper cleanup and connection management

   ```python
   # Good
   async with get_session() as session:
       # operations here

   # Bad - manual session management
   session = create_session()
   # operations
   session.close()  # Easy to forget!
   ```

3. **Use select() for queries**: Modern SQLAlchemy 2.0 style

   ```python
   # Good - SQLAlchemy 2.0 style
   result = await session.execute(select(User).where(User.id == 1))
   user = result.scalar_one()

   # Old - SQLAlchemy 1.x style (avoid)
   user = session.query(User).filter(User.id == 1).one()
   ```

4. **Handle exceptions properly**: Always be prepared for database errors

   ```python
   from sqlalchemy.exc import IntegrityError

   try:
       session.add(user)
       await session.commit()
   except IntegrityError:
       await session.rollback()
       # Handle duplicate email, etc.
   ```

5. **Use scalar_one_or_none() for single results**: Prevents exceptions on missing data

   ```python
   # Good - returns None if not found
   user = result.scalar_one_or_none()
   if user is None:
       # handle not found

   # Bad - raises exception if not found
   user = result.scalar_one()  # Will raise if no result
   ```

6. **Refresh after commit to get generated values**: Get auto-generated IDs and defaults

   ```python
   session.add(user)
   await session.commit()
   await session.refresh(user)  # Now user.id is populated
   ```

7. **Use relationships for related data**: Let SQLAlchemy handle joins

   ```python
   # Good - use relationships
   author = result.scalar_one()
   books = author.books  # SQLAlchemy handles the query

   # Less efficient - manual joins
   books = await session.execute(
       select(Book).where(Book.author_id == author.id)
   )
   ```

8. **Index frequently queried columns**: Improve query performance

   ```python
   email = Column(String(255), unique=True, index=True)  # Indexed for fast lookups
   ```

## Development vs Production

### Development Configuration

```bash
# SQLite for local development (fast and simple)
export DATABASE_URL="sqlite:///./dev.db"

# Or in-memory for testing
export DATABASE_URL="sqlite:///:memory:"
```

### Production Configuration

```bash
# PostgreSQL for production (recommended)
export DATABASE_URL="postgresql://username:password@hostname:5432/database"

# With connection pool settings
export DATABASE_URL="postgresql://username:password@hostname:5432/database?pool_size=20&max_overflow=0"
```

### Database Initialization

In production, ensure migrations are run before starting the application:

```bash
# Run all pending migrations
make run_migrations

# Start your application
python -m beenative.www  # or celery, etc.
```

## Schema Documentation

This schema is automatically generated with [Paracelsus](https://github.com/tedivm/paracelsus). To update:

```bash
make document_schema
```

<!-- BEGIN_SQLALCHEMY_DOCS -->
```mermaid
erDiagram
  plants {
    INTEGER id PK
    VARCHAR all_common_names "nullable"
    JSON bloom_months "nullable"
    VARCHAR flower_colors "nullable"
    FLOAT height_max_ft "nullable"
    FLOAT height_min_ft "nullable"
    VARCHAR height_str "nullable"
    BOOLEAN is_native "nullable"
    VARCHAR moisture_categories "nullable"
    JSON ncbg_images "nullable"
    VARCHAR ncbg_permalink "nullable"
    VARCHAR ncsu_appendage "nullable"
    VARCHAR ncsu_attracts "nullable"
    VARCHAR ncsu_available_space_to_plant "nullable"
    VARCHAR ncsu_bark_color "nullable"
    VARCHAR ncsu_bark_description "nullable"
    VARCHAR ncsu_bark_plate_shape "nullable"
    VARCHAR ncsu_bulb_storage "nullable"
    VARCHAR ncsu_causes_contact_dermatitis "nullable"
    VARCHAR ncsu_climbing_method "nullable"
    VARCHAR ncsu_country_or_region_of_origin "nullable"
    VARCHAR ncsu_cultivars "nullable"
    VARCHAR ncsu_deciduous_leaf_fall_color "nullable"
    VARCHAR ncsu_description "nullable"
    VARCHAR ncsu_design_feature "nullable"
    JSON ncsu_dimensions "nullable"
    VARCHAR ncsu_display_harvest_time "nullable"
    VARCHAR ncsu_distribution "nullable"
    VARCHAR ncsu_edibility "nullable"
    VARCHAR ncsu_family "nullable"
    VARCHAR ncsu_fire_risk_rating "nullable"
    VARCHAR ncsu_flower_bloom_time "nullable"
    VARCHAR ncsu_flower_color "nullable"
    VARCHAR ncsu_flower_description "nullable"
    VARCHAR ncsu_flower_inflorescence "nullable"
    VARCHAR ncsu_flower_petals "nullable"
    VARCHAR ncsu_flower_shape "nullable"
    VARCHAR ncsu_flower_size "nullable"
    VARCHAR ncsu_flower_value_to_gardener "nullable"
    VARCHAR ncsu_fruit_color "nullable"
    VARCHAR ncsu_fruit_description "nullable"
    VARCHAR ncsu_fruit_length "nullable"
    VARCHAR ncsu_fruit_type "nullable"
    VARCHAR ncsu_fruit_value_to_gardener "nullable"
    VARCHAR ncsu_fruit_width "nullable"
    VARCHAR ncsu_genus "nullable"
    VARCHAR ncsu_growth_rate "nullable"
    VARCHAR ncsu_habit_form "nullable"
    VARCHAR ncsu_hairs_present "nullable"
    VARCHAR ncsu_html_description "nullable"
    JSON ncsu_images "nullable"
    VARCHAR ncsu_landscape_location "nullable"
    VARCHAR ncsu_landscape_theme "nullable"
    VARCHAR ncsu_leaf_arrangement "nullable"
    VARCHAR ncsu_leaf_color "nullable"
    VARCHAR ncsu_leaf_description "nullable"
    VARCHAR ncsu_leaf_feel "nullable"
    VARCHAR ncsu_leaf_length "nullable"
    VARCHAR ncsu_leaf_margin "nullable"
    VARCHAR ncsu_leaf_shape "nullable"
    VARCHAR ncsu_leaf_type "nullable"
    VARCHAR ncsu_leaf_value_to_gardener "nullable"
    VARCHAR ncsu_leaf_width "nullable"
    VARCHAR ncsu_life_cycle "nullable"
    VARCHAR ncsu_light "nullable"
    VARCHAR ncsu_maintenance "nullable"
    VARCHAR ncsu_nc_region "nullable"
    VARCHAR ncsu_other_common_names "nullable"
    VARCHAR ncsu_particularly_resistant_to_insects_diseases_other_problems "nullable"
    VARCHAR ncsu_phonetic_spelling "nullable"
    VARCHAR ncsu_pith_split_longitudinally "nullable"
    VARCHAR ncsu_plant_type "nullable"
    VARCHAR ncsu_play_value "nullable"
    VARCHAR ncsu_poison_part "nullable"
    VARCHAR ncsu_poison_severity "nullable"
    VARCHAR ncsu_poison_symptoms "nullable"
    VARCHAR ncsu_poison_toxic_principle "nullable"
    VARCHAR ncsu_problems "nullable"
    VARCHAR ncsu_recommended_propagation_strategy "nullable"
    VARCHAR ncsu_resistance_to_challenges "nullable"
    VARCHAR ncsu_soil_drainage "nullable"
    VARCHAR ncsu_soil_ph "nullable"
    VARCHAR ncsu_soil_texture "nullable"
    VARCHAR ncsu_species "nullable"
    VARCHAR ncsu_stem_bud_scales "nullable"
    VARCHAR ncsu_stem_bud_terminal "nullable"
    VARCHAR ncsu_stem_buds "nullable"
    VARCHAR ncsu_stem_color "nullable"
    VARCHAR ncsu_stem_cross_section "nullable"
    VARCHAR ncsu_stem_description "nullable"
    VARCHAR ncsu_stem_form "nullable"
    VARCHAR ncsu_stem_is_aromatic "nullable"
    VARCHAR ncsu_stem_leaf_scar_shape "nullable"
    VARCHAR ncsu_stem_lenticels "nullable"
    VARCHAR ncsu_stem_surface "nullable"
    VARCHAR ncsu_surface_attachment "nullable"
    VARCHAR ncsu_texture "nullable"
    VARCHAR ncsu_url "nullable"
    VARCHAR ncsu_usda_plant_hardiness_zone "nullable"
    VARCHAR ncsu_uses_ethnobotany "nullable"
    VARCHAR ncsu_wildlife_value "nullable"
    VARCHAR ncsu_woody_plant_leaf_characteristics "nullable"
    VARCHAR plant_categories "nullable"
    VARCHAR plant_resistances "nullable"
    VARCHAR pm_about "nullable"
    BOOLEAN pm_adv_bee "nullable"
    BOOLEAN pm_adv_bird "nullable"
    BOOLEAN pm_adv_deer "nullable"
    BOOLEAN pm_adv_stars "nullable"
    VARCHAR pm_bloom_color "nullable"
    VARCHAR pm_bloom_time "nullable"
    VARCHAR pm_catalog_code "nullable"
    VARCHAR pm_common_name "nullable"
    VARCHAR pm_germination_code "nullable"
    VARCHAR pm_height "nullable"
    VARCHAR pm_image_url "nullable"
    VARCHAR pm_life_cycle "nullable"
    VARCHAR pm_native_states "nullable"
    VARCHAR pm_soil_moisture "nullable"
    VARCHAR pm_sun_exposure "nullable"
    VARCHAR pm_url "nullable"
    VARCHAR primary_lifecycle "nullable"
    VARCHAR scientific_name UK "indexed"
    VARCHAR sunlight_categories "nullable"
    VARCHAR vasc_abundance "nullable"
    VARCHAR vasc_author "nullable"
    VARCHAR vasc_common_name_primary "nullable"
    VARCHAR vasc_distribution "nullable"
    VARCHAR vasc_global_rank "nullable"
    VARCHAR vasc_habitat "nullable"
    VARCHAR vasc_id "nullable"
    VARCHAR vasc_identification "nullable"
    VARCHAR vasc_map_file_path "nullable"
    VARCHAR vasc_map_file_url "nullable"
    VARCHAR vasc_other_common_names "nullable"
    VARCHAR vasc_other_common_names_clean "nullable"
    VARCHAR vasc_phenology "nullable"
    VARCHAR vasc_state_rank "nullable"
    VARCHAR vasc_state_status "nullable"
    VARCHAR vasc_taxonomic_comments "nullable"
    VARCHAR vasc_us_status "nullable"
    VARCHAR vasc_usace_agcp "nullable"
    VARCHAR vasc_usace_emp "nullable"
    FLOAT width_max_ft "nullable"
    FLOAT width_min_ft "nullable"
    VARCHAR width_str "nullable"
    VARCHAR wildlife_attracts "nullable"
  }


```
<!-- END_SQLALCHEMY_DOCS -->

## References

- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/en/20/)
- [SQLAlchemy ORM Documentation](https://docs.sqlalchemy.org/en/20/orm/)
- [SQLAlchemy Async Documentation](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
- [Alembic Tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html)
