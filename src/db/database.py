import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from urllib.parse import quote_plus

import asyncpg
from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
    delete,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings import POSTGRES_CREDS

ROOT_CATEGORY_NAME = "Комплектующие ПК и серверов"

metadata = MetaData()

categories_table = Table(
    "categories",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("parent_id", Integer, ForeignKey("categories.id", ondelete="RESTRICT")),
    UniqueConstraint("parent_id", "name", name="uq_categories_parent_name"),
)

products_table = Table(
    "products",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("category_id", Integer, ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
    Column("price", Numeric(12, 2), nullable=False),
    Column("quantity", Integer, nullable=False, server_default="0"),
    Column("description", String(1000)),
    CheckConstraint("price >= 0", name="ck_products_price_non_negative"),
    CheckConstraint("quantity >= 0", name="ck_products_quantity_non_negative"),
    UniqueConstraint("category_id", "name", name="uq_products_category_name"),
)

enumerations_table = Table(
    "enumerations",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("description", String(1000)),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    UniqueConstraint("name", name="uq_enumerations_name"),
)

enumeration_values_table = Table(
    "enumeration_values",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "enum_id",
        Integer,
        ForeignKey(
            "enumerations.id",
            ondelete="CASCADE",
            name="fk_enumeration_values_enum_id",
        ),
        nullable=False,
    ),
    Column("item_type", String(20), nullable=False, server_default="value"),
    Column("value", String(255)),
    Column(
        "child_enum_id",
        Integer,
        ForeignKey(
            "enumerations.id",
            ondelete="CASCADE",
            name="fk_enumeration_values_child_enum_id",
        ),
    ),
    Column("priority", Integer, nullable=False, server_default="0"),
    Column("description", String(1000)),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    CheckConstraint("priority >= 0", name="ck_enumeration_values_priority_non_negative"),
    CheckConstraint("item_type IN ('value', 'enum')", name="ck_enumeration_values_item_type"),
    CheckConstraint(
        "(item_type = 'value' AND value IS NOT NULL AND child_enum_id IS NULL) OR "
        "(item_type = 'enum' AND value IS NULL AND child_enum_id IS NOT NULL)",
        name="ck_enumeration_values_payload_by_type",
    ),
    CheckConstraint(
        "child_enum_id IS NULL OR enum_id <> child_enum_id",
        name="ck_enumeration_values_not_self_child",
    ),
    UniqueConstraint("enum_id", "value", name="uq_enumeration_values_enum_value"),
    UniqueConstraint("enum_id", "child_enum_id", name="uq_enumeration_values_enum_child"),
)

measurement_units_table = Table(
    "measurement_units",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("full_name", String(255), nullable=False),
    Column("short_name", String(50), nullable=False),
    Column("description", String(1000)),
    UniqueConstraint("full_name", name="uq_measurement_units_full_name"),
    UniqueConstraint("short_name", name="uq_measurement_units_short_name"),
)

parameters_table = Table(
    "parameters",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(255), nullable=False),
    Column("name", String(255), nullable=False),
    Column("description", String(1000)),
    Column("parameter_type", String(20), nullable=False),
    Column(
        "unit_id",
        Integer,
        ForeignKey(
            "measurement_units.id",
            ondelete="RESTRICT",
            name="fk_parameters_unit_id",
        ),
    ),
    Column(
        "enum_id",
        Integer,
        ForeignKey(
            "enumerations.id",
            ondelete="RESTRICT",
            name="fk_parameters_enum_id",
        ),
    ),
    CheckConstraint(
        "parameter_type IN ('integer', 'real', 'string', 'datetime', 'enum')",
        name="ck_parameters_type",
    ),
    CheckConstraint(
        "("
        "parameter_type = 'enum' AND enum_id IS NOT NULL AND unit_id IS NULL"
        ") OR ("
        "parameter_type IN ('integer', 'real') AND enum_id IS NULL"
        ") OR ("
        "parameter_type IN ('string', 'datetime') AND enum_id IS NULL AND unit_id IS NULL"
        ")",
        name="ck_parameters_type_references",
    ),
    UniqueConstraint("code", name="uq_parameters_code"),
)

category_parameters_table = Table(
    "category_parameters",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "category_id",
        Integer,
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "parameter_id",
        Integer,
        ForeignKey("parameters.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("priority", Integer, nullable=False, server_default="0"),
    Column("is_required", Integer, nullable=False, server_default="0"),
    Column("is_inherited", Integer, nullable=False, server_default="0"),
    Column("source_category_id", Integer, ForeignKey("categories.id", ondelete="SET NULL")),
    Column("min_value", Numeric(18, 6)),
    Column("max_value", Numeric(18, 6)),
    CheckConstraint("priority >= 0", name="ck_category_parameters_priority_non_negative"),
    CheckConstraint("is_required IN (0, 1)", name="ck_category_parameters_is_required_bool"),
    CheckConstraint("is_inherited IN (0, 1)", name="ck_category_parameters_is_inherited_bool"),
    CheckConstraint(
        "min_value IS NULL OR max_value IS NULL OR min_value <= max_value",
        name="ck_category_parameters_min_le_max",
    ),
    UniqueConstraint("category_id", "parameter_id", name="uq_category_parameters_category_parameter"),
)

product_parameter_values_table = Table(
    "product_parameter_values",
    metadata,
    Column("id", Integer, primary_key=True),
    Column(
        "product_id",
        Integer,
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "parameter_id",
        Integer,
        ForeignKey("parameters.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("val_real", Numeric(18, 6)),
    Column("val_int", Integer),
    Column("val_str", String(1000)),
    Column("val_datetime", DateTime),
    Column(
        "enum_value_id",
        Integer,
        ForeignKey("enumeration_values.id", ondelete="RESTRICT"),
    ),
    CheckConstraint(
        "("
        "(val_real IS NOT NULL)::int + "
        "(val_int IS NOT NULL)::int + "
        "(val_str IS NOT NULL)::int + "
        "(val_datetime IS NOT NULL)::int + "
        "(enum_value_id IS NOT NULL)::int"
        ") = 1",
        name="ck_product_parameter_values_exactly_one_value",
    ),
    UniqueConstraint("product_id", "parameter_id", name="uq_product_parameter_values_product_parameter"),
)

specifications_table = Table(
    "specifications",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("value", String(1000)),
    Column(
        "enum_value_id",
        Integer,
        ForeignKey(
            "enumeration_values.id",
            ondelete="RESTRICT",
            name="fk_specifications_enum_value_id",
        ),
    ),
    Column(
        "unit_id",
        Integer,
        ForeignKey(
            "measurement_units.id",
            ondelete="RESTRICT",
            name="fk_specifications_unit_id",
        ),
    ),
    Column("custom_unit_full_name", String(255)),
    Column("custom_unit_short_name", String(50)),
    CheckConstraint(
        "(value IS NOT NULL AND enum_value_id IS NULL) OR "
        "(value IS NULL AND enum_value_id IS NOT NULL)",
        name="ck_specifications_value_xor_enum_value_id",
    ),
    CheckConstraint(
        "(unit_id IS NULL) OR "
        "(custom_unit_full_name IS NULL AND custom_unit_short_name IS NULL)",
        name="ck_specifications_unit_id_xor_custom_unit",
    ),
    CheckConstraint(
        "(custom_unit_full_name IS NULL AND custom_unit_short_name IS NULL) OR "
        "(custom_unit_full_name IS NOT NULL AND custom_unit_short_name IS NOT NULL)",
        name="ck_specifications_custom_unit_complete",
    ),
    CheckConstraint(
        "enum_value_id IS NULL OR "
        "(unit_id IS NULL AND custom_unit_full_name IS NULL AND custom_unit_short_name IS NULL)",
        name="ck_specifications_enum_value_without_unit",
    ),
)

product_specifications_table = Table(
    "product_specifications",
    metadata,
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "specification_id",
        Integer,
        ForeignKey("specifications.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


class TreeError(ValueError):
    pass


def get_postgres_creds() -> dict[str, str]:
    return {
        "user": os.getenv("POSTGRES_USER", POSTGRES_CREDS["user"]),
        "password": os.getenv("POSTGRES_PASSWORD", POSTGRES_CREDS["password"]),
        "host": os.getenv("POSTGRES_HOST", POSTGRES_CREDS["host"]),
        "port": os.getenv("POSTGRES_PORT", POSTGRES_CREDS["port"]),
        "database": os.getenv("POSTGRES_DB", POSTGRES_CREDS["database"]),
    }


def build_database_url(database: str | None = None) -> str:
    creds = get_postgres_creds()
    db_name = database or creds["database"]
    return (
        "postgresql+asyncpg://"
        f"{creds['user']}:{quote_plus(creds['password'])}"
        f"@{creds['host']}:{creds['port']}/{db_name}"
    )


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            build_database_url(),
            echo=False,
            pool_pre_ping=True,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
        )
    return _session_factory


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with get_session_factory()() as session:
        yield session


async def create_global_database() -> None:
    creds = get_postgres_creds()
    db_name = creds["database"]
    conn = None

    for attempt in range(10):
        try:
            conn = await asyncpg.connect(
                user=creds["user"],
                password=creds["password"],
                host=creds["host"],
                port=int(creds["port"]),
                database="postgres",
            )
            break
        except Exception:
            if attempt == 9:
                raise
            await asyncio.sleep(2)

    if conn is None:
        raise RuntimeError("Failed to connect to PostgreSQL")

    try:
        exists = await conn.fetchval(
            "SELECT 1 FROM pg_database WHERE datname = $1",
            db_name,
        )
        if not exists:
            await conn.execute(f'CREATE DATABASE "{db_name.replace(chr(34), chr(34) * 2)}"')
    finally:
        await conn.close()


async def create_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async with get_session_factory()() as session:
        await ensure_root_category(session)
        await prepare_enumerations_schema(session)
        await migrate_legacy_specifications(session)
        await prepare_specifications_schema(session)
        await session.commit()


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


def _row_to_category_dict(row) -> dict[str, object]:
    return {
        "id": int(row.id),
        "name": str(row.name),
        "parent_id": int(row.parent_id) if row.parent_id is not None else None,
    }


def _row_to_spec_dict(row) -> dict[str, object]:
    return {
        "id": int(row.id),
        "name": str(row.name),
        "value": str(row.value) if row.value is not None else None,
        "enum_value_id": int(row.enum_value_id) if row.enum_value_id is not None else None,
        "unit_id": int(row.unit_id) if row.unit_id is not None else None,
        "custom_unit_full_name": (
            str(row.custom_unit_full_name) if row.custom_unit_full_name is not None else None
        ),
        "custom_unit_short_name": (
            str(row.custom_unit_short_name) if row.custom_unit_short_name is not None else None
        ),
    }


def _row_to_measurement_unit_dict(row) -> dict[str, object]:
    return {
        "id": int(row.id),
        "full_name": str(row.full_name),
        "short_name": str(row.short_name),
        "description": row.description,
    }


def _row_to_parameter_dict(row) -> dict[str, object]:
    return {
        "id": int(row.id),
        "code": str(row.code),
        "name": str(row.name),
        "description": row.description,
        "parameter_type": str(row.parameter_type),
        "unit_id": int(row.unit_id) if row.unit_id is not None else None,
        "enum_id": int(row.enum_id) if row.enum_id is not None else None,
    }


def _row_to_category_parameter_dict(row) -> dict[str, object]:
    parameter = None
    if "code" in row:
        parameter = {
            "id": int(row.parameter_id),
            "code": str(row.code),
            "name": str(row.name),
            "description": row.description,
            "parameter_type": str(row.parameter_type),
            "unit_id": int(row.unit_id) if row.unit_id is not None else None,
            "enum_id": int(row.enum_id) if row.enum_id is not None else None,
        }
    return {
        "id": int(row.id),
        "category_id": int(row.category_id),
        "parameter_id": int(row.parameter_id),
        "priority": int(row.priority),
        "is_required": bool(row.is_required),
        "is_inherited": bool(row.is_inherited),
        "source_category_id": (
            int(row.source_category_id) if row.source_category_id is not None else None
        ),
        "min_value": float(row.min_value) if row.min_value is not None else None,
        "max_value": float(row.max_value) if row.max_value is not None else None,
        "parameter": parameter,
    }


def _row_to_product_parameter_value_dict(row) -> dict[str, object]:
    parameter = None
    if "code" in row:
        parameter = {
            "id": int(row.parameter_id),
            "code": str(row.code),
            "name": str(row.name),
            "description": row.description,
            "parameter_type": str(row.parameter_type),
            "unit_id": int(row.unit_id) if row.unit_id is not None else None,
            "enum_id": int(row.enum_id) if row.enum_id is not None else None,
        }
    return {
        "id": int(row.id),
        "product_id": int(row.product_id),
        "parameter_id": int(row.parameter_id),
        "val_real": float(row.val_real) if row.val_real is not None else None,
        "val_int": int(row.val_int) if row.val_int is not None else None,
        "val_str": str(row.val_str) if row.val_str is not None else None,
        "val_datetime": row.val_datetime,
        "enum_value_id": int(row.enum_value_id) if row.enum_value_id is not None else None,
        "parameter": parameter,
    }


def _row_to_enumeration_dict(row) -> dict[str, object]:
    return {
        "id": int(row.id),
        "name": str(row.name),
        "description": row.description,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _row_to_enumeration_value_dict(row) -> dict[str, object]:
    child_enum_id = int(row.child_enum_id) if row.child_enum_id is not None else None
    child_name = row["child_name"] if "child_name" in row else None
    child_description = row["child_description"] if "child_description" in row else None
    return {
        "id": int(row.id),
        "enum_id": int(row.enum_id),
        "item_type": str(row.item_type),
        "value": str(row.value) if row.value is not None else None,
        "child_enum_id": child_enum_id,
        "child_name": str(child_name) if child_name is not None else None,
        "child_description": child_description,
        "priority": int(row.priority),
        "description": row.description,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _decimal_to_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


async def prepare_enumerations_schema(session: AsyncSession) -> None:
    await session.execute(
        text("ALTER TABLE enumeration_values ADD COLUMN IF NOT EXISTS item_type VARCHAR(20)")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values ADD COLUMN IF NOT EXISTS child_enum_id INTEGER")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values ALTER COLUMN item_type SET DEFAULT 'value'")
    )
    await session.execute(
        text("UPDATE enumeration_values SET item_type = 'value' WHERE item_type IS NULL")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values ALTER COLUMN item_type SET NOT NULL")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values ALTER COLUMN value DROP NOT NULL")
    )
    await session.execute(
        text(
            """
            DO $$
            BEGIN
                IF to_regclass('public.enumeration_children') IS NOT NULL THEN
                    INSERT INTO enumeration_values (
                        enum_id,
                        item_type,
                        value,
                        child_enum_id,
                        priority,
                        description,
                        created_at,
                        updated_at
                    )
                    SELECT
                        enum_id,
                        'enum',
                        NULL,
                        child_enum_id,
                        priority,
                        description,
                        created_at,
                        updated_at
                    FROM enumeration_children ec
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM enumeration_values ev
                        WHERE ev.enum_id = ec.enum_id
                          AND ev.child_enum_id = ec.child_enum_id
                    );
                END IF;
            END $$;
            """
        )
    )
    await session.execute(
        text("ALTER TABLE enumeration_values DROP CONSTRAINT IF EXISTS fk_enumeration_values_child_enum_id")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values DROP CONSTRAINT IF EXISTS ck_enumeration_values_item_type")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values DROP CONSTRAINT IF EXISTS ck_enumeration_values_payload_by_type")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values DROP CONSTRAINT IF EXISTS ck_enumeration_values_not_self_child")
    )
    await session.execute(
        text("ALTER TABLE enumeration_values DROP CONSTRAINT IF EXISTS uq_enumeration_values_enum_child")
    )
    await session.execute(
        text(
            """
            ALTER TABLE enumeration_values
            ADD CONSTRAINT fk_enumeration_values_child_enum_id
            FOREIGN KEY (child_enum_id)
            REFERENCES enumerations(id)
            ON DELETE CASCADE
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE enumeration_values
            ADD CONSTRAINT ck_enumeration_values_item_type
            CHECK (item_type IN ('value', 'enum'))
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE enumeration_values
            ADD CONSTRAINT ck_enumeration_values_payload_by_type
            CHECK (
                (item_type = 'value' AND value IS NOT NULL AND child_enum_id IS NULL)
                OR
                (item_type = 'enum' AND value IS NULL AND child_enum_id IS NOT NULL)
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE enumeration_values
            ADD CONSTRAINT ck_enumeration_values_not_self_child
            CHECK (child_enum_id IS NULL OR enum_id <> child_enum_id)
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE enumeration_values
            ADD CONSTRAINT uq_enumeration_values_enum_child
            UNIQUE (enum_id, child_enum_id)
            """
        )
    )
    await session.execute(text("DROP TABLE IF EXISTS enumeration_children"))


async def prepare_specifications_schema(session: AsyncSession) -> None:
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS specifications_product_id_fkey")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP COLUMN IF EXISTS product_id")
    )
    await session.execute(
        text("ALTER TABLE specifications ADD COLUMN IF NOT EXISTS enum_value_id INTEGER")
    )
    await session.execute(
        text("ALTER TABLE specifications ADD COLUMN IF NOT EXISTS unit_id INTEGER")
    )
    await session.execute(
        text("ALTER TABLE specifications ADD COLUMN IF NOT EXISTS custom_unit_full_name VARCHAR(255)")
    )
    await session.execute(
        text("ALTER TABLE specifications ADD COLUMN IF NOT EXISTS custom_unit_short_name VARCHAR(50)")
    )
    await session.execute(
        text("ALTER TABLE specifications ALTER COLUMN value DROP NOT NULL")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS ck_specifications_value_xor_enum_value_id")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS fk_specifications_enum_value_id")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS fk_specifications_unit_id")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS ck_specifications_unit_id_xor_custom_unit")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS ck_specifications_custom_unit_complete")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS ck_specifications_enum_value_without_unit")
    )
    await session.execute(
        text(
            """
            ALTER TABLE specifications
            ADD CONSTRAINT fk_specifications_enum_value_id
            FOREIGN KEY (enum_value_id)
            REFERENCES enumeration_values(id)
            ON DELETE RESTRICT
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE specifications
            ADD CONSTRAINT fk_specifications_unit_id
            FOREIGN KEY (unit_id)
            REFERENCES measurement_units(id)
            ON DELETE RESTRICT
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE specifications
            ADD CONSTRAINT ck_specifications_value_xor_enum_value_id
            CHECK (
                (value IS NOT NULL AND enum_value_id IS NULL)
                OR
                (value IS NULL AND enum_value_id IS NOT NULL)
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE specifications
            ADD CONSTRAINT ck_specifications_unit_id_xor_custom_unit
            CHECK (
                (unit_id IS NULL)
                OR
                (custom_unit_full_name IS NULL AND custom_unit_short_name IS NULL)
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE specifications
            ADD CONSTRAINT ck_specifications_custom_unit_complete
            CHECK (
                (custom_unit_full_name IS NULL AND custom_unit_short_name IS NULL)
                OR
                (custom_unit_full_name IS NOT NULL AND custom_unit_short_name IS NOT NULL)
            )
            """
        )
    )
    await session.execute(
        text(
            """
            ALTER TABLE specifications
            ADD CONSTRAINT ck_specifications_enum_value_without_unit
            CHECK (
                enum_value_id IS NULL
                OR
                (
                    unit_id IS NULL
                    AND custom_unit_full_name IS NULL
                    AND custom_unit_short_name IS NULL
                )
            )
            """
        )
    )


async def ensure_root_category(session: AsyncSession) -> int:
    root_id = await session.scalar(
        select(categories_table.c.id).where(
            categories_table.c.parent_id.is_(None),
            categories_table.c.name == ROOT_CATEGORY_NAME,
        )
    )
    if root_id is None:
        result = await session.execute(
            insert(categories_table)
            .values(name=ROOT_CATEGORY_NAME, parent_id=None)
            .returning(categories_table.c.id)
        )
        root_id = int(result.scalar_one())
    else:
        root_id = int(root_id)

    # Repair old data created before the dedicated root logic:
    # every top-level category except the real root becomes its child.
    orphan_rows = await session.execute(
        select(categories_table.c.id, categories_table.c.name).where(
            categories_table.c.parent_id.is_(None),
            categories_table.c.id != root_id,
        )
    )
    for orphan in orphan_rows:
        duplicate_id = await session.scalar(
            select(categories_table.c.id).where(
                categories_table.c.parent_id == root_id,
                func.lower(categories_table.c.name) == orphan.name.lower(),
            )
        )
        if duplicate_id is not None:
            continue
        await session.execute(
            update(categories_table)
            .where(categories_table.c.id == orphan.id)
            .values(parent_id=root_id)
        )

    return root_id


async def _get_category_row(session: AsyncSession, category_id: int):
    result = await session.execute(
        select(categories_table).where(categories_table.c.id == category_id)
    )
    return result.mappings().first()


async def _get_product_row(session: AsyncSession, product_id: int):
    result = await session.execute(
        select(products_table).where(products_table.c.id == product_id)
    )
    return result.mappings().first()


async def _get_specification_row(session: AsyncSession, specification_id: int):
    result = await session.execute(
        select(specifications_table).where(specifications_table.c.id == specification_id)
    )
    return result.mappings().first()


async def _get_measurement_unit_row(session: AsyncSession, unit_id: int):
    result = await session.execute(
        select(measurement_units_table).where(measurement_units_table.c.id == unit_id)
    )
    return result.mappings().first()


async def _get_parameter_row(session: AsyncSession, parameter_id: int):
    result = await session.execute(
        select(parameters_table).where(parameters_table.c.id == parameter_id)
    )
    return result.mappings().first()


async def _get_category_parameter_row(session: AsyncSession, category_parameter_id: int):
    result = await session.execute(
        select(category_parameters_table).where(
            category_parameters_table.c.id == category_parameter_id
        )
    )
    return result.mappings().first()


async def _get_product_parameter_value_row(
    session: AsyncSession,
    *,
    product_id: int,
    parameter_id: int,
):
    result = await session.execute(
        select(product_parameter_values_table).where(
            product_parameter_values_table.c.product_id == product_id,
            product_parameter_values_table.c.parameter_id == parameter_id,
        )
    )
    return result.mappings().first()


async def _get_enumeration_row(session: AsyncSession, enumeration_id: int):
    result = await session.execute(
        select(enumerations_table).where(enumerations_table.c.id == enumeration_id)
    )
    return result.mappings().first()


async def _get_enumeration_value_row(session: AsyncSession, value_id: int):
    result = await session.execute(
        select(enumeration_values_table).where(enumeration_values_table.c.id == value_id)
    )
    return result.mappings().first()


async def _category_exists_with_name(
    session: AsyncSession,
    *,
    parent_id: int | None,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(categories_table.c.id).where(
        categories_table.c.parent_id == parent_id,
        func.lower(categories_table.c.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(categories_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _product_exists_with_name(
    session: AsyncSession,
    *,
    category_id: int,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(products_table.c.id).where(
        products_table.c.category_id == category_id,
        func.lower(products_table.c.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(products_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _measurement_unit_exists(
    session: AsyncSession,
    *,
    full_name: str | None = None,
    short_name: str | None = None,
    exclude_id: int | None = None,
) -> bool:
    conditions = []
    if full_name is not None:
        conditions.append(func.lower(measurement_units_table.c.full_name) == full_name.lower())
    if short_name is not None:
        conditions.append(func.lower(measurement_units_table.c.short_name) == short_name.lower())
    if not conditions:
        return False

    stmt = select(measurement_units_table.c.id).where(*conditions)
    if exclude_id is not None:
        stmt = stmt.where(measurement_units_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _parameter_exists_with_code(
    session: AsyncSession,
    *,
    code: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(parameters_table.c.id).where(
        func.lower(parameters_table.c.code) == code.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(parameters_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _category_parameter_exists(
    session: AsyncSession,
    *,
    category_id: int,
    parameter_id: int,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(category_parameters_table.c.id).where(
        category_parameters_table.c.category_id == category_id,
        category_parameters_table.c.parameter_id == parameter_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(category_parameters_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _get_category_parameter_for_value(
    session: AsyncSession,
    *,
    category_id: int,
    parameter_id: int,
):
    result = await session.execute(
        select(category_parameters_table).where(
            category_parameters_table.c.category_id == category_id,
            category_parameters_table.c.parameter_id == parameter_id,
        )
    )
    return result.mappings().first()


def _validate_numeric_bounds(
    *,
    parameter_type: str,
    min_value: Decimal | None,
    max_value: Decimal | None,
) -> None:
    if parameter_type not in {"integer", "real"} and (
        min_value is not None or max_value is not None
    ):
        raise TreeError("Ограничения min/max можно задавать только для числовых параметров")
    if min_value is not None and max_value is not None and min_value > max_value:
        raise TreeError("Минимальное значение параметра не может быть больше максимального")


async def _enumeration_exists_with_name(
    session: AsyncSession,
    *,
    name: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(enumerations_table.c.id).where(
        func.lower(enumerations_table.c.name) == name.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(enumerations_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _enumeration_value_exists(
    session: AsyncSession,
    *,
    enum_id: int,
    value: str,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(enumeration_values_table.c.id).where(
        enumeration_values_table.c.enum_id == enum_id,
        func.lower(enumeration_values_table.c.value) == value.lower(),
    )
    if exclude_id is not None:
        stmt = stmt.where(enumeration_values_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _enumeration_child_item_exists(
    session: AsyncSession,
    *,
    enum_id: int,
    child_enum_id: int,
    exclude_id: int | None = None,
) -> bool:
    stmt = select(enumeration_values_table.c.id).where(
        enumeration_values_table.c.enum_id == enum_id,
        enumeration_values_table.c.item_type == "enum",
        enumeration_values_table.c.child_enum_id == child_enum_id,
    )
    if exclude_id is not None:
        stmt = stmt.where(enumeration_values_table.c.id != exclude_id)
    return await session.scalar(stmt) is not None


async def _enumeration_contains_child(
    session: AsyncSession,
    *,
    enum_id: int,
    target_enum_id: int,
) -> bool:
    pending = [enum_id]
    visited: set[int] = set()

    while pending:
        current_enum_id = pending.pop()
        if current_enum_id in visited:
            continue
        visited.add(current_enum_id)

        result = await session.execute(
            select(enumeration_values_table.c.child_enum_id).where(
                enumeration_values_table.c.enum_id == current_enum_id,
                enumeration_values_table.c.item_type == "enum",
            )
        )
        for row in result:
            if row.child_enum_id is None:
                continue
            child_enum_id = int(row.child_enum_id)
            if child_enum_id == target_enum_id:
                return True
            pending.append(child_enum_id)

    return False


async def _find_canonical_specification_id(
    session: AsyncSession,
    *,
    name: str,
    value: str | None = None,
    enum_value_id: int | None = None,
    unit_id: int | None = None,
    custom_unit_full_name: str | None = None,
    custom_unit_short_name: str | None = None,
) -> int | None:
    stmt = select(specifications_table.c.id).where(
        func.lower(specifications_table.c.name) == name.lower(),
    )
    if enum_value_id is not None:
        stmt = stmt.where(
            specifications_table.c.value.is_(None),
            specifications_table.c.enum_value_id == enum_value_id,
            specifications_table.c.unit_id.is_(None),
            specifications_table.c.custom_unit_full_name.is_(None),
            specifications_table.c.custom_unit_short_name.is_(None),
        )
    else:
        stmt = stmt.where(
            specifications_table.c.value == value,
            specifications_table.c.enum_value_id.is_(None),
            specifications_table.c.unit_id == unit_id
            if unit_id is not None
            else specifications_table.c.unit_id.is_(None),
            specifications_table.c.custom_unit_full_name == custom_unit_full_name
            if custom_unit_full_name is not None
            else specifications_table.c.custom_unit_full_name.is_(None),
            specifications_table.c.custom_unit_short_name == custom_unit_short_name
            if custom_unit_short_name is not None
            else specifications_table.c.custom_unit_short_name.is_(None),
        )
    return await session.scalar(stmt)


async def _get_or_create_canonical_specification(
    session: AsyncSession,
    *,
    name: str,
    value: str | None = None,
    enum_value_id: int | None = None,
    unit_id: int | None = None,
    custom_unit_full_name: str | None = None,
    custom_unit_short_name: str | None = None,
) -> dict[str, object]:
    canonical_id = await _find_canonical_specification_id(
        session,
        name=name,
        value=value,
        enum_value_id=enum_value_id,
        unit_id=unit_id,
        custom_unit_full_name=custom_unit_full_name,
        custom_unit_short_name=custom_unit_short_name,
    )
    if canonical_id is None:
        spec_values: dict[str, object] = {"name": name.strip()}
        if enum_value_id is not None:
            spec_values["enum_value_id"] = enum_value_id
        else:
            spec_values["value"] = value.strip() if value is not None else None
            if unit_id is not None:
                spec_values["unit_id"] = unit_id
            elif custom_unit_full_name is not None and custom_unit_short_name is not None:
                spec_values["custom_unit_full_name"] = custom_unit_full_name.strip()
                spec_values["custom_unit_short_name"] = custom_unit_short_name.strip()
        result = await session.execute(
            insert(specifications_table)
            .values(**spec_values)
            .returning(specifications_table)
        )
        row = result.mappings().one()
        return _row_to_spec_dict(row)

    row = await _get_specification_row(session, int(canonical_id))
    if row is None:
        raise RuntimeError("Canonical specification not found after lookup")
    return _row_to_spec_dict(row)


async def resolve_specification_references(
    session: AsyncSession,
    specifications: list[dict[str, object]],
) -> list[dict[str, object]]:
    resolved_specs: list[dict[str, object]] = []

    for raw_spec in specifications:
        specification_id = raw_spec.get("specification_id")
        if specification_id is not None:
            row = await _get_specification_row(session, int(specification_id))
            if row is None:
                raise TreeError(f"Спецификация с id={specification_id} не найдена")
            resolved_specs.append(
                await _get_or_create_canonical_specification(
                    session,
                    name=str(row["name"]),
                    value=str(row["value"]) if row["value"] is not None else None,
                    enum_value_id=(
                        int(row["enum_value_id"]) if row["enum_value_id"] is not None else None
                    ),
                    unit_id=int(row["unit_id"]) if row["unit_id"] is not None else None,
                    custom_unit_full_name=(
                        str(row["custom_unit_full_name"])
                        if row["custom_unit_full_name"] is not None
                        else None
                    ),
                    custom_unit_short_name=(
                        str(row["custom_unit_short_name"])
                        if row["custom_unit_short_name"] is not None
                        else None
                    ),
                )
            )
            continue

        enum_value_id = raw_spec.get("enum_value_id")
        if enum_value_id is not None:
            enum_value = await _get_enumeration_value_row(session, int(enum_value_id))
            if enum_value is None:
                raise TreeError(f"Значение перечисления с id={enum_value_id} не найдено")
            if enum_value["item_type"] != "value":
                raise TreeError(
                    f"Значение перечисления с id={enum_value_id} не является конечным значением"
                )
            resolved_specs.append(
                await _get_or_create_canonical_specification(
                    session,
                    name=str(raw_spec["name"]),
                    enum_value_id=int(enum_value_id),
                )
            )
            continue

        unit_id = raw_spec.get("unit_id")
        custom_unit_full_name = raw_spec.get("custom_unit_full_name")
        custom_unit_short_name = raw_spec.get("custom_unit_short_name")
        if unit_id is not None:
            unit = await _get_measurement_unit_row(session, int(unit_id))
            if unit is None:
                raise TreeError(f"Единица измерения с id={unit_id} не найдена")

        resolved_specs.append(
            await _get_or_create_canonical_specification(
                session,
                name=str(raw_spec["name"]),
                value=str(raw_spec["value"]),
                unit_id=int(unit_id) if unit_id is not None else None,
                custom_unit_full_name=(
                    str(custom_unit_full_name) if custom_unit_full_name is not None else None
                ),
                custom_unit_short_name=(
                    str(custom_unit_short_name) if custom_unit_short_name is not None else None
                ),
            )
        )

    unique_specs: dict[int, dict[str, object]] = {}
    for spec in resolved_specs:
        unique_specs[int(spec["id"])] = spec
    return list(unique_specs.values())


async def migrate_legacy_specifications(session: AsyncSession) -> None:
    has_legacy_column = await session.scalar(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'specifications'
                  AND column_name = 'product_id'
            )
            """
        )
    )
    if not has_legacy_column:
        return

    legacy_specs_result = await session.execute(
        text(
            """
            SELECT id, product_id, name, value
            FROM specifications
            WHERE product_id IS NOT NULL
            """
        )
    )
    legacy_specs = legacy_specs_result.mappings().all()

    for legacy_spec in legacy_specs:
        canonical_spec = await _get_or_create_canonical_specification(
            session,
            name=str(legacy_spec["name"]),
            value=str(legacy_spec["value"]),
        )
        link_exists = await session.scalar(
            select(product_specifications_table.c.product_id).where(
                product_specifications_table.c.product_id == int(legacy_spec["product_id"]),
                product_specifications_table.c.specification_id == int(canonical_spec["id"]),
            )
        )
        if link_exists is None:
            await session.execute(
                insert(product_specifications_table).values(
                    product_id=int(legacy_spec["product_id"]),
                    specification_id=int(canonical_spec["id"]),
                )
            )


async def create_measurement_unit(
    *,
    full_name: str,
    short_name: str,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        if await _measurement_unit_exists(session, full_name=full_name):
            raise TreeError(
                f"Нельзя создать единицу измерения: полное название '{full_name}' уже используется"
            )
        if await _measurement_unit_exists(session, short_name=short_name):
            raise TreeError(
                f"Нельзя создать единицу измерения: сокращение '{short_name}' уже используется"
            )

        result = await session.execute(
            insert(measurement_units_table)
            .values(
                full_name=full_name.strip(),
                short_name=short_name.strip(),
                description=description.strip() if description else None,
            )
            .returning(measurement_units_table)
        )
        await session.commit()
        return _row_to_measurement_unit_dict(result.mappings().one())


async def list_measurement_units() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(measurement_units_table).order_by(
                measurement_units_table.c.full_name,
                measurement_units_table.c.id,
            )
        )
        return [_row_to_measurement_unit_dict(row) for row in result.mappings().all()]


async def get_measurement_unit(unit_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        row = await _get_measurement_unit_row(session, unit_id)
        if row is None:
            raise TreeError(f"Единица измерения с id={unit_id} не найдена")
        return _row_to_measurement_unit_dict(row)


async def update_measurement_unit(
    unit_id: int,
    *,
    full_name: str,
    short_name: str,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        unit = await _get_measurement_unit_row(session, unit_id)
        if unit is None:
            raise TreeError(f"Нельзя изменить единицу измерения: id={unit_id} не найден")
        if await _measurement_unit_exists(
            session,
            full_name=full_name,
            exclude_id=unit_id,
        ):
            raise TreeError(
                f"Нельзя изменить единицу измерения: полное название '{full_name}' уже используется"
            )
        if await _measurement_unit_exists(
            session,
            short_name=short_name,
            exclude_id=unit_id,
        ):
            raise TreeError(
                f"Нельзя изменить единицу измерения: сокращение '{short_name}' уже используется"
            )

        result = await session.execute(
            update(measurement_units_table)
            .where(measurement_units_table.c.id == unit_id)
            .values(
                full_name=full_name.strip(),
                short_name=short_name.strip(),
                description=description.strip() if description else None,
            )
            .returning(measurement_units_table)
        )
        await session.commit()
        return _row_to_measurement_unit_dict(result.mappings().one())


async def delete_measurement_unit(unit_id: int) -> None:
    async with get_session_factory()() as session:
        unit = await _get_measurement_unit_row(session, unit_id)
        if unit is None:
            raise TreeError(f"Нельзя удалить единицу измерения: id={unit_id} не найден")

        used_specification_id = await session.scalar(
            select(specifications_table.c.id).where(specifications_table.c.unit_id == unit_id)
        )
        if used_specification_id is not None:
            raise TreeError("Нельзя удалить единицу измерения: она используется в спецификациях")

        used_parameter_id = await session.scalar(
            select(parameters_table.c.id).where(parameters_table.c.unit_id == unit_id)
        )
        if used_parameter_id is not None:
            raise TreeError("Нельзя удалить единицу измерения: она используется в параметрах")

        await session.execute(
            delete(measurement_units_table).where(measurement_units_table.c.id == unit_id)
        )
        await session.commit()


async def _validate_parameter_references(
    session: AsyncSession,
    *,
    parameter_type: str,
    unit_id: int | None,
    enum_id: int | None,
) -> None:
    if parameter_type not in {"integer", "real", "string", "datetime", "enum"}:
        raise TreeError("Недопустимый тип параметра")

    if parameter_type == "enum":
        if enum_id is None:
            raise TreeError("Для параметра типа enum нужно указать enum_id")
        if unit_id is not None:
            raise TreeError("Для параметра типа enum нельзя указывать unit_id")
        enumeration = await _get_enumeration_row(session, enum_id)
        if enumeration is None:
            raise TreeError(f"Перечисление с id={enum_id} не найдено")
        return

    if enum_id is not None:
        raise TreeError("enum_id можно указывать только для параметра типа enum")

    if parameter_type in {"string", "datetime"} and unit_id is not None:
        raise TreeError("unit_id можно указывать только для числовых параметров")

    if unit_id is not None:
        unit = await _get_measurement_unit_row(session, unit_id)
        if unit is None:
            raise TreeError(f"Единица измерения с id={unit_id} не найдена")


async def create_parameter(
    *,
    code: str,
    name: str,
    description: str | None,
    parameter_type: str,
    unit_id: int | None,
    enum_id: int | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        if await _parameter_exists_with_code(session, code=code):
            raise TreeError(f"Нельзя создать параметр: код '{code}' уже используется")

        await _validate_parameter_references(
            session,
            parameter_type=parameter_type,
            unit_id=unit_id,
            enum_id=enum_id,
        )

        result = await session.execute(
            insert(parameters_table)
            .values(
                code=code.strip(),
                name=name.strip(),
                description=description.strip() if description else None,
                parameter_type=parameter_type,
                unit_id=unit_id,
                enum_id=enum_id,
            )
            .returning(parameters_table)
        )
        await session.commit()
        return _row_to_parameter_dict(result.mappings().one())


async def list_parameters() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(parameters_table).order_by(parameters_table.c.code, parameters_table.c.id)
        )
        return [_row_to_parameter_dict(row) for row in result.mappings().all()]


async def get_parameter(parameter_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        row = await _get_parameter_row(session, parameter_id)
        if row is None:
            raise TreeError(f"Параметр с id={parameter_id} не найден")
        return _row_to_parameter_dict(row)


async def update_parameter(
    parameter_id: int,
    *,
    code: str,
    name: str,
    description: str | None,
    parameter_type: str,
    unit_id: int | None,
    enum_id: int | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        parameter = await _get_parameter_row(session, parameter_id)
        if parameter is None:
            raise TreeError(f"Нельзя изменить параметр: id={parameter_id} не найден")

        if await _parameter_exists_with_code(
            session,
            code=code,
            exclude_id=parameter_id,
        ):
            raise TreeError(f"Нельзя изменить параметр: код '{code}' уже используется")

        await _validate_parameter_references(
            session,
            parameter_type=parameter_type,
            unit_id=unit_id,
            enum_id=enum_id,
        )

        result = await session.execute(
            update(parameters_table)
            .where(parameters_table.c.id == parameter_id)
            .values(
                code=code.strip(),
                name=name.strip(),
                description=description.strip() if description else None,
                parameter_type=parameter_type,
                unit_id=unit_id,
                enum_id=enum_id,
            )
            .returning(parameters_table)
        )
        await session.commit()
        return _row_to_parameter_dict(result.mappings().one())


async def delete_parameter(parameter_id: int) -> None:
    async with get_session_factory()() as session:
        parameter = await _get_parameter_row(session, parameter_id)
        if parameter is None:
            raise TreeError(f"Нельзя удалить параметр: id={parameter_id} не найден")

        used_category_parameter_id = await session.scalar(
            select(category_parameters_table.c.id).where(
                category_parameters_table.c.parameter_id == parameter_id
            )
        )
        if used_category_parameter_id is not None:
            raise TreeError("Нельзя удалить параметр: он назначен категориям")

        used_product_value_id = await session.scalar(
            select(product_parameter_values_table.c.id).where(
                product_parameter_values_table.c.parameter_id == parameter_id
            )
        )
        if used_product_value_id is not None:
            raise TreeError("Нельзя удалить параметр: по нему есть значения изделий")

        await session.execute(delete(parameters_table).where(parameters_table.c.id == parameter_id))
        await session.commit()


async def assign_parameter_to_category(
    *,
    category_id: int,
    parameter_id: int,
    priority: int,
    is_required: bool,
    is_inherited: bool = False,
    source_category_id: int | None = None,
    min_value: Decimal | None = None,
    max_value: Decimal | None = None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Категория с id={category_id} не найдена")
        parameter = await _get_parameter_row(session, parameter_id)
        if parameter is None:
            raise TreeError(f"Параметр с id={parameter_id} не найден")
        if await _category_parameter_exists(
            session,
            category_id=category_id,
            parameter_id=parameter_id,
        ):
            raise TreeError("Параметр уже назначен этой категории")

        if source_category_id is not None:
            source_category = await _get_category_row(session, source_category_id)
            if source_category is None:
                raise TreeError(f"Категория-источник с id={source_category_id} не найдена")

        _validate_numeric_bounds(
            parameter_type=str(parameter["parameter_type"]),
            min_value=min_value,
            max_value=max_value,
        )

        result = await session.execute(
            insert(category_parameters_table)
            .values(
                category_id=category_id,
                parameter_id=parameter_id,
                priority=priority,
                is_required=1 if is_required else 0,
                is_inherited=1 if is_inherited else 0,
                source_category_id=source_category_id,
                min_value=min_value,
                max_value=max_value,
            )
            .returning(category_parameters_table)
        )
        await session.commit()
        return _row_to_category_parameter_dict(result.mappings().one())


async def list_category_parameters(category_id: int) -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Категория с id={category_id} не найдена")

        result = await session.execute(
            select(
                category_parameters_table,
                parameters_table.c.code,
                parameters_table.c.name,
                parameters_table.c.description,
                parameters_table.c.parameter_type,
                parameters_table.c.unit_id,
                parameters_table.c.enum_id,
            )
            .join(parameters_table, parameters_table.c.id == category_parameters_table.c.parameter_id)
            .where(category_parameters_table.c.category_id == category_id)
            .order_by(category_parameters_table.c.priority, parameters_table.c.code)
        )
        return [_row_to_category_parameter_dict(row) for row in result.mappings().all()]


async def update_category_parameter(
    category_parameter_id: int,
    *,
    priority: int,
    is_required: bool,
    min_value: Decimal | None,
    max_value: Decimal | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        category_parameter = await _get_category_parameter_row(session, category_parameter_id)
        if category_parameter is None:
            raise TreeError(
                f"Назначение параметра категории с id={category_parameter_id} не найдено"
            )
        parameter = await _get_parameter_row(session, int(category_parameter["parameter_id"]))
        if parameter is None:
            raise TreeError("Связанный параметр не найден")

        _validate_numeric_bounds(
            parameter_type=str(parameter["parameter_type"]),
            min_value=min_value,
            max_value=max_value,
        )

        result = await session.execute(
            update(category_parameters_table)
            .where(category_parameters_table.c.id == category_parameter_id)
            .values(
                priority=priority,
                is_required=1 if is_required else 0,
                min_value=min_value,
                max_value=max_value,
            )
            .returning(category_parameters_table)
        )
        await session.commit()
        return _row_to_category_parameter_dict(result.mappings().one())


async def remove_parameter_from_category(category_parameter_id: int) -> None:
    async with get_session_factory()() as session:
        category_parameter = await _get_category_parameter_row(session, category_parameter_id)
        if category_parameter is None:
            raise TreeError(
                f"Назначение параметра категории с id={category_parameter_id} не найдено"
            )
        used_value_id = await session.scalar(
            select(product_parameter_values_table.c.id).where(
                product_parameter_values_table.c.parameter_id == int(category_parameter["parameter_id"])
            )
        )
        if used_value_id is not None:
            raise TreeError("Нельзя удалить параметр из категории: по нему уже есть значения изделий")
        await session.execute(
            delete(category_parameters_table).where(
                category_parameters_table.c.id == category_parameter_id
            )
        )
        await session.commit()


async def copy_category_parameters(category_id: int) -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Категория с id={category_id} не найдена")
        parent_id = category["parent_id"]
        if parent_id is None:
            raise TreeError("У корневой категории нет родителя для копирования параметров")

        parent_parameters = await session.execute(
            select(category_parameters_table).where(
                category_parameters_table.c.category_id == int(parent_id)
            )
        )
        for parent_parameter in parent_parameters.mappings().all():
            parameter_id = int(parent_parameter["parameter_id"])
            if await _category_parameter_exists(
                session,
                category_id=category_id,
                parameter_id=parameter_id,
            ):
                continue
            await session.execute(
                insert(category_parameters_table).values(
                    category_id=category_id,
                    parameter_id=parameter_id,
                    priority=int(parent_parameter["priority"]),
                    is_required=int(parent_parameter["is_required"]),
                    is_inherited=1,
                    source_category_id=int(parent_id),
                    min_value=parent_parameter["min_value"],
                    max_value=parent_parameter["max_value"],
                )
            )
        await session.commit()

    return await list_category_parameters(category_id)


def _count_parameter_value_fields(
    *,
    val_real: Decimal | None,
    val_int: int | None,
    val_str: str | None,
    val_datetime: datetime | None,
    enum_value_id: int | None,
) -> int:
    return sum(
        value is not None
        for value in [val_real, val_int, val_str, val_datetime, enum_value_id]
    )


async def _validate_product_parameter_value(
    session: AsyncSession,
    *,
    product,
    parameter,
    category_parameter,
    val_real: Decimal | None,
    val_int: int | None,
    val_str: str | None,
    val_datetime: datetime | None,
    enum_value_id: int | None,
) -> dict[str, object]:
    if _count_parameter_value_fields(
        val_real=val_real,
        val_int=val_int,
        val_str=val_str,
        val_datetime=val_datetime,
        enum_value_id=enum_value_id,
    ) != 1:
        raise TreeError("Нужно передать ровно одно значение параметра")

    parameter_type = str(parameter["parameter_type"])
    values: dict[str, object] = {
        "val_real": None,
        "val_int": None,
        "val_str": None,
        "val_datetime": None,
        "enum_value_id": None,
    }

    if parameter_type == "integer":
        if val_int is None:
            raise TreeError("Для параметра integer нужно передать val_int")
        decimal_value = Decimal(val_int)
        min_value = category_parameter["min_value"]
        max_value = category_parameter["max_value"]
        if min_value is not None and decimal_value < min_value:
            raise TreeError("Значение параметра меньше минимально допустимого")
        if max_value is not None and decimal_value > max_value:
            raise TreeError("Значение параметра больше максимально допустимого")
        values["val_int"] = val_int
        return values

    if parameter_type == "real":
        if val_real is None:
            raise TreeError("Для параметра real нужно передать val_real")
        min_value = category_parameter["min_value"]
        max_value = category_parameter["max_value"]
        if min_value is not None and val_real < min_value:
            raise TreeError("Значение параметра меньше минимально допустимого")
        if max_value is not None and val_real > max_value:
            raise TreeError("Значение параметра больше максимально допустимого")
        values["val_real"] = val_real
        return values

    if parameter_type == "string":
        if val_str is None:
            raise TreeError("Для параметра string нужно передать val_str")
        normalized = val_str.strip()
        if not normalized:
            raise TreeError("Строковое значение параметра не должно быть пустым")
        values["val_str"] = normalized
        return values

    if parameter_type == "datetime":
        if val_datetime is None:
            raise TreeError("Для параметра datetime нужно передать val_datetime")
        values["val_datetime"] = val_datetime
        return values

    if parameter_type == "enum":
        if enum_value_id is None:
            raise TreeError("Для параметра enum нужно передать enum_value_id")
        enum_value = await _get_enumeration_value_row(session, enum_value_id)
        if enum_value is None:
            raise TreeError(f"Значение перечисления с id={enum_value_id} не найдено")
        if enum_value["item_type"] != "value":
            raise TreeError("Параметр enum должен ссылаться на конечное значение перечисления")
        if int(enum_value["enum_id"]) != int(parameter["enum_id"]):
            raise TreeError("Значение перечисления не относится к перечислению параметра")
        values["enum_value_id"] = enum_value_id
        return values

    raise TreeError("Недопустимый тип параметра")


async def set_product_parameter_value(
    *,
    product_id: int,
    parameter_id: int,
    val_real: Decimal | None = None,
    val_int: int | None = None,
    val_str: str | None = None,
    val_datetime: datetime | None = None,
    enum_value_id: int | None = None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(f"Комплектующее с id={product_id} не найдено")
        parameter = await _get_parameter_row(session, parameter_id)
        if parameter is None:
            raise TreeError(f"Параметр с id={parameter_id} не найден")
        category_parameter = await _get_category_parameter_for_value(
            session,
            category_id=int(product["category_id"]),
            parameter_id=parameter_id,
        )
        if category_parameter is None:
            raise TreeError("Параметр не назначен категории данного изделия")

        values = await _validate_product_parameter_value(
            session,
            product=product,
            parameter=parameter,
            category_parameter=category_parameter,
            val_real=val_real,
            val_int=val_int,
            val_str=val_str,
            val_datetime=val_datetime,
            enum_value_id=enum_value_id,
        )

        existing_value = await _get_product_parameter_value_row(
            session,
            product_id=product_id,
            parameter_id=parameter_id,
        )
        if existing_value is None:
            result = await session.execute(
                insert(product_parameter_values_table)
                .values(product_id=product_id, parameter_id=parameter_id, **values)
                .returning(product_parameter_values_table.c.id)
            )
            value_id = int(result.scalar_one())
        else:
            value_id = int(existing_value["id"])
            await session.execute(
                update(product_parameter_values_table)
                .where(product_parameter_values_table.c.id == value_id)
                .values(**values)
            )
        await session.commit()

    values = await list_product_parameter_values(product_id)
    for value in values:
        if int(value["id"]) == value_id:
            return value
    raise RuntimeError("Product parameter value not found after save")


async def list_product_parameter_values(product_id: int) -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(f"Комплектующее с id={product_id} не найдено")

        result = await session.execute(
            select(
                product_parameter_values_table,
                parameters_table.c.code,
                parameters_table.c.name,
                parameters_table.c.description,
                parameters_table.c.parameter_type,
                parameters_table.c.unit_id,
                parameters_table.c.enum_id,
            )
            .join(parameters_table, parameters_table.c.id == product_parameter_values_table.c.parameter_id)
            .where(product_parameter_values_table.c.product_id == product_id)
            .order_by(parameters_table.c.code)
        )
        return [_row_to_product_parameter_value_dict(row) for row in result.mappings().all()]


async def delete_product_parameter_value(product_id: int, parameter_id: int) -> None:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(f"Комплектующее с id={product_id} не найдено")
        parameter_value = await _get_product_parameter_value_row(
            session,
            product_id=product_id,
            parameter_id=parameter_id,
        )
        if parameter_value is None:
            raise TreeError("Значение параметра изделия не найдено")
        await session.execute(
            delete(product_parameter_values_table).where(
                product_parameter_values_table.c.id == int(parameter_value["id"])
            )
        )
        await session.commit()


async def _product_matches_parameter_filter(
    value: dict[str, object] | None,
    parameter,
    raw_filter: dict[str, object],
) -> bool:
    if value is None:
        return False

    operator = str(raw_filter.get("operator", "eq"))
    parameter_type = str(parameter["parameter_type"])

    if parameter_type == "integer":
        actual = value["val_int"]
        expected = raw_filter.get("val_int")
    elif parameter_type == "real":
        actual = value["val_real"]
        expected = raw_filter.get("val_real")
    elif parameter_type == "string":
        actual = value["val_str"]
        expected = raw_filter.get("val_str")
    elif parameter_type == "datetime":
        actual = value["val_datetime"]
        expected = raw_filter.get("val_datetime")
    elif parameter_type == "enum":
        actual = value["enum_value_id"]
        expected = raw_filter.get("enum_value_id")
    else:
        return False

    if actual is None or expected is None:
        return False

    if operator == "eq":
        return actual == expected
    if operator == "contains" and parameter_type == "string":
        return str(expected).lower() in str(actual).lower()
    if operator == "gte" and parameter_type in {"integer", "real", "datetime"}:
        return actual >= expected
    if operator == "lte" and parameter_type in {"integer", "real", "datetime"}:
        return actual <= expected
    raise TreeError("Недопустимый оператор фильтра для типа параметра")


async def list_products_by_category_with_parameters(category_id: int) -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Категория с id={category_id} не найдена")

        products_result = await session.execute(
            select(products_table)
            .where(products_table.c.category_id == category_id)
            .order_by(products_table.c.name)
        )
        products = products_result.mappings().all()

    result: list[dict[str, object]] = []
    for product in products:
        product_payload = await get_product(int(product["id"]))
        product_payload["parameter_values"] = await list_product_parameter_values(int(product["id"]))
        result.append(product_payload)
    return result


async def filter_products_by_parameters(
    *,
    category_id: int,
    filters: list[dict[str, object]],
) -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Категория с id={category_id} не найдена")

        parameter_ids = [int(raw_filter["parameter_id"]) for raw_filter in filters]
        parameters_by_id: dict[int, object] = {}
        for parameter_id in parameter_ids:
            parameter = await _get_parameter_row(session, parameter_id)
            if parameter is None:
                raise TreeError(f"Параметр с id={parameter_id} не найден")
            category_parameter = await _get_category_parameter_for_value(
                session,
                category_id=category_id,
                parameter_id=parameter_id,
            )
            if category_parameter is None:
                raise TreeError(f"Параметр id={parameter_id} не назначен категории id={category_id}")
            parameters_by_id[parameter_id] = parameter

    products = await list_products_by_category_with_parameters(category_id)
    filtered_products: list[dict[str, object]] = []

    for product in products:
        values_by_parameter_id = {
            int(value["parameter_id"]): value for value in product["parameter_values"]
        }
        matched = True
        for raw_filter in filters:
            parameter_id = int(raw_filter["parameter_id"])
            if not await _product_matches_parameter_filter(
                values_by_parameter_id.get(parameter_id),
                parameters_by_id[parameter_id],
                raw_filter,
            ):
                matched = False
                break
        if matched:
            filtered_products.append(product)

    return filtered_products


async def list_categories() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(categories_table).order_by(categories_table.c.parent_id, categories_table.c.name)
        )
        return [_row_to_category_dict(row) for row in result.mappings().all()]


async def get_category(category_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        row = await _get_category_row(session, category_id)
        if row is None:
            raise TreeError(f"Категория с id={category_id} не найдена")
        return _row_to_category_dict(row)


async def create_enumeration(
    *,
    name: str,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        if await _enumeration_exists_with_name(session, name=name):
            raise TreeError(f"Нельзя создать перечисление: имя '{name}' уже используется")

        result = await session.execute(
            insert(enumerations_table)
            .values(
                name=name.strip(),
                description=description.strip() if description else None,
            )
            .returning(enumerations_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_enumeration_dict(row)


async def list_enumerations() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(enumerations_table).order_by(enumerations_table.c.name, enumerations_table.c.id)
        )
        return [_row_to_enumeration_dict(row) for row in result.mappings().all()]


async def get_enumeration(enumeration_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        row = await _get_enumeration_row(session, enumeration_id)
        if row is None:
            raise TreeError(f"Перечисление с id={enumeration_id} не найдено")
        return _row_to_enumeration_dict(row)


async def update_enumeration(
    enumeration_id: int,
    *,
    name: str,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        enumeration = await _get_enumeration_row(session, enumeration_id)
        if enumeration is None:
            raise TreeError(f"Нельзя изменить перечисление: id={enumeration_id} не найден")

        if await _enumeration_exists_with_name(
            session,
            name=name,
            exclude_id=enumeration_id,
        ):
            raise TreeError(f"Нельзя изменить перечисление: имя '{name}' уже используется")

        result = await session.execute(
            update(enumerations_table)
            .where(enumerations_table.c.id == enumeration_id)
            .values(
                name=name.strip(),
                description=description.strip() if description else None,
                updated_at=func.now(),
            )
            .returning(enumerations_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_enumeration_dict(row)


async def delete_enumeration(enumeration_id: int) -> None:
    async with get_session_factory()() as session:
        enumeration = await _get_enumeration_row(session, enumeration_id)
        if enumeration is None:
            raise TreeError(f"Нельзя удалить перечисление: id={enumeration_id} не найден")

        used_parameter_id = await session.scalar(
            select(parameters_table.c.id).where(parameters_table.c.enum_id == enumeration_id)
        )
        if used_parameter_id is not None:
            raise TreeError("Нельзя удалить перечисление: оно используется в параметрах")

        await session.execute(
            delete(enumerations_table).where(enumerations_table.c.id == enumeration_id)
        )
        await session.commit()


async def list_enumeration_values(enum_id: int) -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        enumeration = await _get_enumeration_row(session, enum_id)
        if enumeration is None:
            raise TreeError(f"Перечисление с id={enum_id} не найдено")

        result = await session.execute(
            select(
                enumeration_values_table.c.id,
                enumeration_values_table.c.enum_id,
                enumeration_values_table.c.item_type,
                enumeration_values_table.c.value,
                enumeration_values_table.c.child_enum_id,
                enumerations_table.c.name.label("child_name"),
                enumerations_table.c.description.label("child_description"),
                enumeration_values_table.c.priority,
                enumeration_values_table.c.description,
                enumeration_values_table.c.created_at,
                enumeration_values_table.c.updated_at,
            )
            .outerjoin(
                enumerations_table,
                enumerations_table.c.id == enumeration_values_table.c.child_enum_id,
            )
            .where(enumeration_values_table.c.enum_id == enum_id)
            .order_by(
                enumeration_values_table.c.priority,
                enumeration_values_table.c.value,
                enumerations_table.c.name,
                enumeration_values_table.c.id,
            )
        )
        return [_row_to_enumeration_value_dict(row) for row in result.mappings().all()]


async def create_enumeration_value(
    *,
    enum_id: int,
    item_type: str,
    value: str | None,
    child_enum_id: int | None,
    priority: int,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        enumeration = await _get_enumeration_row(session, enum_id)
        if enumeration is None:
            raise TreeError(
                f"Нельзя создать значение перечисления: перечисление с id={enum_id} не найдено"
            )

        values: dict[str, object] = {
            "enum_id": enum_id,
            "item_type": item_type,
            "priority": priority,
            "description": description.strip() if description else None,
        }
        if item_type == "value":
            if value is None:
                raise TreeError("Нельзя создать значение перечисления: поле value обязательно")
            if await _enumeration_value_exists(session, enum_id=enum_id, value=value):
                raise TreeError(
                    f"Нельзя создать значение перечисления: значение '{value}' уже существует в перечислении id={enum_id}"
                )
            values["value"] = value.strip()
        elif item_type == "enum":
            if child_enum_id is None:
                raise TreeError("Нельзя создать значение перечисления: поле child_enum_id обязательно")
            child_enumeration = await _get_enumeration_row(session, child_enum_id)
            if child_enumeration is None:
                raise TreeError(
                    f"Нельзя создать значение перечисления: дочернее перечисление id={child_enum_id} не найдено"
                )
            if enum_id == child_enum_id:
                raise TreeError("Нельзя добавить перечисление внутрь самого себя")
            if await _enumeration_child_item_exists(
                session,
                enum_id=enum_id,
                child_enum_id=child_enum_id,
            ):
                raise TreeError(
                    f"Нельзя создать значение перечисления: enum id={child_enum_id} уже добавлен в перечисление id={enum_id}"
                )
            if await _enumeration_contains_child(
                session,
                enum_id=child_enum_id,
                target_enum_id=enum_id,
            ):
                raise TreeError("Нельзя добавить вложенное перечисление: операция создает цикл")
            values["child_enum_id"] = child_enum_id
        else:
            raise TreeError("Нельзя создать значение перечисления: неизвестный item_type")

        result = await session.execute(
            insert(enumeration_values_table)
            .values(**values)
            .returning(enumeration_values_table.c.id)
        )
        value_id = int(result.scalar_one())
        await session.commit()
        return await get_enumeration_value(value_id)


async def get_enumeration_value(value_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(
                enumeration_values_table.c.id,
                enumeration_values_table.c.enum_id,
                enumeration_values_table.c.item_type,
                enumeration_values_table.c.value,
                enumeration_values_table.c.child_enum_id,
                enumerations_table.c.name.label("child_name"),
                enumerations_table.c.description.label("child_description"),
                enumeration_values_table.c.priority,
                enumeration_values_table.c.description,
                enumeration_values_table.c.created_at,
                enumeration_values_table.c.updated_at,
            )
            .outerjoin(
                enumerations_table,
                enumerations_table.c.id == enumeration_values_table.c.child_enum_id,
            )
            .where(enumeration_values_table.c.id == value_id)
        )
        row = result.mappings().first()
        if row is None:
            raise TreeError(f"Значение перечисления с id={value_id} не найдено")
        return _row_to_enumeration_value_dict(row)


async def update_enumeration_value(
    value_id: int,
    *,
    item_type: str,
    value: str | None,
    child_enum_id: int | None,
    priority: int,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        enumeration_value = await _get_enumeration_value_row(session, value_id)
        if enumeration_value is None:
            raise TreeError(f"Нельзя изменить значение перечисления: id={value_id} не найден")

        enum_id = int(enumeration_value["enum_id"])
        values: dict[str, object] = {
            "item_type": item_type,
            "value": None,
            "child_enum_id": None,
            "priority": priority,
            "description": description.strip() if description else None,
            "updated_at": func.now(),
        }
        if item_type == "value":
            if value is None:
                raise TreeError("Нельзя изменить значение перечисления: поле value обязательно")
            if await _enumeration_value_exists(
                session,
                enum_id=enum_id,
                value=value,
                exclude_id=value_id,
            ):
                raise TreeError(
                    f"Нельзя изменить значение перечисления: значение '{value}' уже существует в перечислении id={enum_id}"
                )
            values["value"] = value.strip()
        elif item_type == "enum":
            if child_enum_id is None:
                raise TreeError("Нельзя изменить значение перечисления: поле child_enum_id обязательно")
            child_enumeration = await _get_enumeration_row(session, child_enum_id)
            if child_enumeration is None:
                raise TreeError(
                    f"Нельзя изменить значение перечисления: дочернее перечисление id={child_enum_id} не найдено"
                )
            if enum_id == child_enum_id:
                raise TreeError("Нельзя добавить перечисление внутрь самого себя")
            if await _enumeration_child_item_exists(
                session,
                enum_id=enum_id,
                child_enum_id=child_enum_id,
                exclude_id=value_id,
            ):
                raise TreeError(
                    f"Нельзя изменить значение перечисления: enum id={child_enum_id} уже добавлен в перечисление id={enum_id}"
                )
            if await _enumeration_contains_child(
                session,
                enum_id=child_enum_id,
                target_enum_id=enum_id,
            ):
                raise TreeError("Нельзя добавить вложенное перечисление: операция создает цикл")
            values["child_enum_id"] = child_enum_id
        else:
            raise TreeError("Нельзя изменить значение перечисления: неизвестный item_type")

        await session.execute(
            update(enumeration_values_table)
            .where(enumeration_values_table.c.id == value_id)
            .values(**values)
        )
        await session.commit()
        return await get_enumeration_value(value_id)


async def delete_enumeration_value(value_id: int) -> None:
    async with get_session_factory()() as session:
        enumeration_value = await _get_enumeration_value_row(session, value_id)
        if enumeration_value is None:
            raise TreeError(f"Нельзя удалить значение перечисления: id={value_id} не найден")

        used_product_value_id = await session.scalar(
            select(product_parameter_values_table.c.id).where(
                product_parameter_values_table.c.enum_value_id == value_id
            )
        )
        if used_product_value_id is not None:
            raise TreeError("Нельзя удалить значение перечисления: оно используется в параметрах изделий")

        await session.execute(
            delete(enumeration_values_table).where(enumeration_values_table.c.id == value_id)
        )
        await session.commit()


async def create_category(name: str, parent_id: int | None = None) -> dict[str, object]:
    async with get_session_factory()() as session:
        root_id = await ensure_root_category(session)
        resolved_parent_id = parent_id if parent_id is not None else root_id

        parent = await _get_category_row(session, resolved_parent_id)
        if parent is None:
            raise TreeError(f"Нельзя создать вершину: родитель с id={resolved_parent_id} не найден")

        if await _category_exists_with_name(
            session,
            parent_id=resolved_parent_id,
            name=name,
        ):
            raise TreeError(
                f"Нельзя создать вершину: в родительской категории id={resolved_parent_id} уже есть элемент с именем '{name}'"
            )

        result = await session.execute(
            insert(categories_table)
            .values(name=name.strip(), parent_id=resolved_parent_id)
            .returning(categories_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_category_dict(row)


async def update_category(category_id: int, *, name: str) -> dict[str, object]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Нельзя изменить вершину: категория с id={category_id} не найдена")
        if category["parent_id"] is None:
            raise TreeError("Нельзя переименовать корневую вершину")

        if await _category_exists_with_name(
            session,
            parent_id=category["parent_id"],
            name=name,
            exclude_id=category_id,
        ):
            raise TreeError(
                f"Нельзя изменить вершину: в этой родительской категории уже есть элемент с именем '{name}'"
            )

        result = await session.execute(
            update(categories_table)
            .where(categories_table.c.id == category_id)
            .values(name=name.strip())
            .returning(categories_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_category_dict(row)


async def _is_descendant(
    session: AsyncSession,
    *,
    category_id: int,
    possible_ancestor_id: int,
) -> bool:
    current_id = possible_ancestor_id
    while current_id is not None:
        if current_id == category_id:
            return True
        current_id = await session.scalar(
            select(categories_table.c.parent_id).where(categories_table.c.id == current_id)
        )
    return False


async def move_category(category_id: int, new_parent_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Нельзя переместить вершину: категория с id={category_id} не найдена")
        if category["parent_id"] is None:
            raise TreeError("Нельзя перемещать корневую вершину")

        parent = await _get_category_row(session, new_parent_id)
        if parent is None:
            raise TreeError(
                f"Нельзя переместить вершину: новая родительская категория с id={new_parent_id} не найдена"
            )
        if category_id == new_parent_id:
            raise TreeError("Нельзя переместить вершину в саму себя")
        if await _is_descendant(
            session,
            category_id=category_id,
            possible_ancestor_id=new_parent_id,
        ):
            raise TreeError("Нельзя переместить вершину в собственного потомка")
        if await _category_exists_with_name(
            session,
            parent_id=new_parent_id,
            name=str(category["name"]),
            exclude_id=category_id,
        ):
            raise TreeError(
                f"Нельзя переместить вершину: в целевой категории уже есть элемент с именем '{category['name']}'"
            )

        result = await session.execute(
            update(categories_table)
            .where(categories_table.c.id == category_id)
            .values(parent_id=new_parent_id)
            .returning(categories_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_category_dict(row)


async def delete_category(category_id: int) -> None:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Нельзя удалить вершину: категория с id={category_id} не найдена")
        if category["parent_id"] is None:
            raise TreeError("Нельзя удалить корневую вершину")

        has_children = await session.scalar(
            select(categories_table.c.id).where(categories_table.c.parent_id == category_id)
        )
        if has_children is not None:
            raise TreeError("Нельзя удалить вершину: у нее есть дочерние категории")

        has_products = await session.scalar(
            select(products_table.c.id).where(products_table.c.category_id == category_id)
        )
        if has_products is not None:
            raise TreeError("Нельзя удалить вершину: в ней есть комплектующие")

        await session.execute(
            delete(categories_table).where(categories_table.c.id == category_id)
        )
        await session.commit()


async def create_product(
    *,
    category_id: int,
    name: str,
    price: Decimal,
    quantity: int,
    description: str | None,
    specifications: list[dict[str, object]],
) -> dict[str, object]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(
                f"Нельзя создать комплектующее: категория с id={category_id} не найдена"
            )
        if await _product_exists_with_name(session, category_id=category_id, name=name):
            raise TreeError(
                f"Нельзя создать комплектующее: в категории id={category_id} уже есть товар с именем '{name}'"
            )

        result = await session.execute(
            insert(products_table)
            .values(
                category_id=category_id,
                name=name.strip(),
                price=price,
                quantity=quantity,
                description=description.strip() if description else None,
            )
            .returning(products_table)
        )
        product_row = result.mappings().one()
        product_id = int(product_row["id"])

        resolved_specs = await resolve_specification_references(session, specifications)
        for spec in resolved_specs:
            await session.execute(
                insert(product_specifications_table).values(
                    product_id=product_id,
                    specification_id=int(spec["id"]),
                )
            )

        await session.commit()
        return await get_product(product_id)


async def list_products() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(select(products_table).order_by(products_table.c.name))
        products = result.mappings().all()

    return [await get_product(int(product["id"])) for product in products]


async def get_product(product_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(f"Комплектующее с id={product_id} не найдено")

        specs_result = await session.execute(
            select(specifications_table)
            .join(
                product_specifications_table,
                product_specifications_table.c.specification_id == specifications_table.c.id,
            )
            .where(product_specifications_table.c.product_id == product_id)
            .order_by(specifications_table.c.id)
        )
        return {
            "id": int(product["id"]),
            "name": str(product["name"]),
            "category_id": int(product["category_id"]),
            "price": _decimal_to_float(product["price"]),
            "quantity": int(product["quantity"]),
            "description": product["description"],
            "specifications": [
                _row_to_spec_dict(row) for row in specs_result.mappings().all()
            ],
        }


async def update_product(
    product_id: int,
    *,
    name: str,
    price: Decimal,
    quantity: int,
    description: str | None,
    specifications: list[dict[str, object]],
) -> dict[str, object]:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(f"Нельзя изменить комплектующее: товар с id={product_id} не найден")

        if await _product_exists_with_name(
            session,
            category_id=int(product["category_id"]),
            name=name,
            exclude_id=product_id,
        ):
            raise TreeError(
                f"Нельзя изменить комплектующее: в этой категории уже есть товар с именем '{name}'"
            )

        await session.execute(
            update(products_table)
            .where(products_table.c.id == product_id)
            .values(
                name=name.strip(),
                price=price,
                quantity=quantity,
                description=description.strip() if description else None,
            )
        )
        await session.execute(
            delete(product_specifications_table).where(
                product_specifications_table.c.product_id == product_id
            )
        )
        resolved_specs = await resolve_specification_references(session, specifications)
        for spec in resolved_specs:
            await session.execute(
                insert(product_specifications_table).values(
                    product_id=product_id,
                    specification_id=int(spec["id"]),
                )
            )
        await session.commit()
        return await get_product(product_id)


async def move_product(product_id: int, new_category_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(
                f"Нельзя переместить комплектующее: товар с id={product_id} не найден"
            )

        category = await _get_category_row(session, new_category_id)
        if category is None:
            raise TreeError(
                f"Нельзя переместить комплектующее: категория с id={new_category_id} не найдена"
            )

        if await _product_exists_with_name(
            session,
            category_id=new_category_id,
            name=str(product["name"]),
            exclude_id=product_id,
        ):
            raise TreeError(
                f"Нельзя переместить комплектующее: в целевой категории уже есть товар с именем '{product['name']}'"
            )

        await session.execute(
            update(products_table)
            .where(products_table.c.id == product_id)
            .values(category_id=new_category_id)
        )
        await session.commit()
        return await get_product(product_id)


async def delete_product(product_id: int) -> None:
    async with get_session_factory()() as session:
        product = await _get_product_row(session, product_id)
        if product is None:
            raise TreeError(
                f"Нельзя удалить комплектующее: товар с id={product_id} не найден"
            )
        await session.execute(delete(products_table).where(products_table.c.id == product_id))
        await session.commit()


async def get_database_summary() -> dict[str, object]:
    async with get_session_factory()() as session:
        categories_count = await session.scalar(select(func.count()).select_from(categories_table))
        products_count = await session.scalar(select(func.count()).select_from(products_table))
        specs_count = await session.scalar(select(func.count()).select_from(specifications_table))
        root_id = await ensure_root_category(session)
        await session.commit()
        return {
            "root_category_id": root_id,
            "categories_count": int(categories_count or 0),
            "products_count": int(products_count or 0),
            "specifications_count": int(specs_count or 0),
        }


async def list_specifications() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(specifications_table)
            .order_by(
                specifications_table.c.name,
                specifications_table.c.value,
                specifications_table.c.enum_value_id,
            )
        )
        return [_row_to_spec_dict(row) for row in result.mappings().all()]


async def get_tree() -> dict[str, object]:
    async with get_session_factory()() as session:
        root_id = await ensure_root_category(session)

        categories_result = await session.execute(
            select(categories_table).order_by(categories_table.c.id)
        )
        products_result = await session.execute(
            select(products_table).order_by(products_table.c.id)
        )
        specs_result = await session.execute(
            select(
                product_specifications_table.c.product_id,
                specifications_table.c.id,
                specifications_table.c.name,
                specifications_table.c.value,
                specifications_table.c.enum_value_id,
                specifications_table.c.unit_id,
                specifications_table.c.custom_unit_full_name,
                specifications_table.c.custom_unit_short_name,
            )
            .join(
                specifications_table,
                specifications_table.c.id == product_specifications_table.c.specification_id,
            )
            .order_by(product_specifications_table.c.product_id, specifications_table.c.id)
        )
        await session.commit()

    categories = categories_result.mappings().all()
    products = products_result.mappings().all()
    specifications = specs_result.mappings().all()

    categories_by_id: dict[int, dict[str, object]] = {}
    for row in categories:
        categories_by_id[int(row["id"])] = {
            "id": int(row["id"]),
            "name": str(row["name"]),
            "type": "category",
            "parent_id": int(row["parent_id"]) if row["parent_id"] is not None else None,
            "children": [],
            "products": [],
        }

    specs_by_product: dict[int, list[dict[str, object]]] = {}
    for row in specifications:
        specs_by_product.setdefault(int(row["product_id"]), []).append(
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "value": str(row["value"]) if row["value"] is not None else None,
                "enum_value_id": (
                    int(row["enum_value_id"]) if row["enum_value_id"] is not None else None
                ),
                "unit_id": int(row["unit_id"]) if row["unit_id"] is not None else None,
                "custom_unit_full_name": (
                    str(row["custom_unit_full_name"])
                    if row["custom_unit_full_name"] is not None
                    else None
                ),
                "custom_unit_short_name": (
                    str(row["custom_unit_short_name"])
                    if row["custom_unit_short_name"] is not None
                    else None
                ),
            }
        )

    for row in products:
        category_id = int(row["category_id"])
        category = categories_by_id.get(category_id)
        if category is None:
            continue
        category["products"].append(
            {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "type": "product",
                "category_id": category_id,
                "price": _decimal_to_float(row["price"]),
                "quantity": int(row["quantity"]),
                "description": row["description"],
                "specifications": specs_by_product.get(int(row["id"]), []),
            }
        )

    root_node: dict[str, object] | None = None
    for category in categories_by_id.values():
        parent_id = category["parent_id"]
        if parent_id is None:
            if category["id"] == root_id:
                root_node = category
            continue
        parent = categories_by_id.get(parent_id)
        if parent is not None:
            parent["children"].append(category)

    if root_node is None:
        raise RuntimeError("Root category not found")

    return root_node
