import asyncio
import os
from collections.abc import AsyncIterator
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
    Column("value", String(255), nullable=False),
    Column("priority", Integer, nullable=False, server_default="0"),
    Column("description", String(1000)),
    Column("created_at", DateTime, nullable=False, server_default=func.now()),
    Column("updated_at", DateTime, nullable=False, server_default=func.now()),
    CheckConstraint("priority >= 0", name="ck_enumeration_values_priority_non_negative"),
    UniqueConstraint("enum_id", "value", name="uq_enumeration_values_enum_value"),
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
    CheckConstraint(
        "(value IS NOT NULL AND enum_value_id IS NULL) OR "
        "(value IS NULL AND enum_value_id IS NOT NULL)",
        name="ck_specifications_value_xor_enum_value_id",
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
    return {
        "id": int(row.id),
        "enum_id": int(row.enum_id),
        "value": str(row.value),
        "priority": int(row.priority),
        "description": row.description,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _decimal_to_float(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.01")))


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
        text("ALTER TABLE specifications ALTER COLUMN value DROP NOT NULL")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS ck_specifications_value_xor_enum_value_id")
    )
    await session.execute(
        text("ALTER TABLE specifications DROP CONSTRAINT IF EXISTS fk_specifications_enum_value_id")
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
            ADD CONSTRAINT ck_specifications_value_xor_enum_value_id
            CHECK (
                (value IS NOT NULL AND enum_value_id IS NULL)
                OR
                (value IS NULL AND enum_value_id IS NOT NULL)
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


async def _find_canonical_specification_id(
    session: AsyncSession,
    *,
    name: str,
    value: str | None = None,
    enum_value_id: int | None = None,
) -> int | None:
    stmt = select(specifications_table.c.id).where(
        func.lower(specifications_table.c.name) == name.lower(),
    )
    if enum_value_id is not None:
        stmt = stmt.where(
            specifications_table.c.value.is_(None),
            specifications_table.c.enum_value_id == enum_value_id,
        )
    else:
        stmt = stmt.where(
            specifications_table.c.value == value,
            specifications_table.c.enum_value_id.is_(None),
        )
    return await session.scalar(stmt)


async def _get_or_create_canonical_specification(
    session: AsyncSession,
    *,
    name: str,
    value: str | None = None,
    enum_value_id: int | None = None,
) -> dict[str, object]:
    canonical_id = await _find_canonical_specification_id(
        session,
        name=name,
        value=value,
        enum_value_id=enum_value_id,
    )
    if canonical_id is None:
        spec_values: dict[str, object] = {"name": name.strip()}
        if enum_value_id is not None:
            spec_values["enum_value_id"] = enum_value_id
        else:
            spec_values["value"] = value.strip() if value is not None else None
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
                )
            )
            continue

        enum_value_id = raw_spec.get("enum_value_id")
        if enum_value_id is not None:
            enum_value = await _get_enumeration_value_row(session, int(enum_value_id))
            if enum_value is None:
                raise TreeError(f"Значение перечисления с id={enum_value_id} не найдено")
            resolved_specs.append(
                await _get_or_create_canonical_specification(
                    session,
                    name=str(raw_spec["name"]),
                    enum_value_id=int(enum_value_id),
                )
            )
            continue

        resolved_specs.append(
            await _get_or_create_canonical_specification(
                session,
                name=str(raw_spec["name"]),
                value=str(raw_spec["value"]),
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
            select(enumeration_values_table)
            .where(enumeration_values_table.c.enum_id == enum_id)
            .order_by(
                enumeration_values_table.c.priority,
                enumeration_values_table.c.value,
                enumeration_values_table.c.id,
            )
        )
        return [_row_to_enumeration_value_dict(row) for row in result.mappings().all()]


async def create_enumeration_value(
    *,
    enum_id: int,
    value: str,
    priority: int,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        enumeration = await _get_enumeration_row(session, enum_id)
        if enumeration is None:
            raise TreeError(
                f"Нельзя создать значение перечисления: перечисление с id={enum_id} не найдено"
            )

        if await _enumeration_value_exists(session, enum_id=enum_id, value=value):
            raise TreeError(
                f"Нельзя создать значение перечисления: значение '{value}' уже существует в перечислении id={enum_id}"
            )

        result = await session.execute(
            insert(enumeration_values_table)
            .values(
                enum_id=enum_id,
                value=value.strip(),
                priority=priority,
                description=description.strip() if description else None,
            )
            .returning(enumeration_values_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_enumeration_value_dict(row)


async def get_enumeration_value(value_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        row = await _get_enumeration_value_row(session, value_id)
        if row is None:
            raise TreeError(f"Значение перечисления с id={value_id} не найдено")
        return _row_to_enumeration_value_dict(row)


async def update_enumeration_value(
    value_id: int,
    *,
    value: str,
    priority: int,
    description: str | None,
) -> dict[str, object]:
    async with get_session_factory()() as session:
        enumeration_value = await _get_enumeration_value_row(session, value_id)
        if enumeration_value is None:
            raise TreeError(f"Нельзя изменить значение перечисления: id={value_id} не найден")

        enum_id = int(enumeration_value["enum_id"])
        if await _enumeration_value_exists(
            session,
            enum_id=enum_id,
            value=value,
            exclude_id=value_id,
        ):
            raise TreeError(
                f"Нельзя изменить значение перечисления: значение '{value}' уже существует в перечислении id={enum_id}"
            )

        result = await session.execute(
            update(enumeration_values_table)
            .where(enumeration_values_table.c.id == value_id)
            .values(
                value=value.strip(),
                priority=priority,
                description=description.strip() if description else None,
                updated_at=func.now(),
            )
            .returning(enumeration_values_table)
        )
        await session.commit()
        row = result.mappings().one()
        return _row_to_enumeration_value_dict(row)


async def delete_enumeration_value(value_id: int) -> None:
    async with get_session_factory()() as session:
        enumeration_value = await _get_enumeration_value_row(session, value_id)
        if enumeration_value is None:
            raise TreeError(f"Нельзя удалить значение перечисления: id={value_id} не найден")

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
