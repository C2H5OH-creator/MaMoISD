import asyncio
import os
import re
from collections.abc import AsyncIterator
from urllib.parse import quote_plus

import asyncpg
from sqlalchemy import (
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    insert,
    select,
    text,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from settings import POSTGRES_CREDS

metadata = MetaData()

categories_table = Table(
    "categories",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(255), nullable=False),
    Column("parent_id", Integer, ForeignKey("categories.id", ondelete="CASCADE")),
    UniqueConstraint("parent_id", "name", name="uq_categories_parent_name"),
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None
_TABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def normalize_table_name(value: str) -> str:
    table_name = value.strip()
    if not table_name:
        raise ValueError("table_name is required")
    if not _TABLE_NAME_RE.fullmatch(table_name):
        raise ValueError(
            "Invalid table name. Use letters, numbers, and underscores only."
        )
    return table_name


def quote_table_name(value: str) -> str:
    return _quote_identifier(normalize_table_name(value))


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
    session_factory = get_session_factory()
    async with session_factory() as session:
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
            await conn.execute(f"CREATE DATABASE {_quote_identifier(db_name)}")
    finally:
        await conn.close()


async def create_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def create_categories_table() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(categories_table.create, checkfirst=True)


async def create_subcategories_table() -> None:
    await create_categories_table()


async def create_category_tables() -> None:
    await create_categories_table()


async def create_category(name: str, parent_id: int | None = None) -> int:
    async with get_session_factory()() as session:
        if parent_id is not None:
            parent_exists = await session.scalar(
                select(categories_table.c.id).where(categories_table.c.id == parent_id)
            )
            if parent_exists is None:
                raise ValueError(f"Parent category with id={parent_id} not found")

        result = await session.execute(
            insert(categories_table)
            .values(name=name, parent_id=parent_id)
            .returning(categories_table.c.id)
        )
        await session.commit()
        return int(result.scalar_one())


async def create_subcategory(name: str, parent_id: int) -> int:
    return await create_category(name=name, parent_id=parent_id)


async def create_subcategory_table(
    table_name: str,
    parent_table_name: str,
) -> dict[str, int | str]:
    child_table_name = normalize_table_name(table_name)
    parent_table = normalize_table_name(parent_table_name)
    if child_table_name == parent_table:
        raise ValueError("table_name and parent_table_name must be different")

    q_parent = quote_table_name(parent_table)
    q_child = quote_table_name(child_table_name)

    engine = get_engine()
    async with engine.begin() as conn:
        parent_exists = await conn.scalar(
            text(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": parent_table},
        )
        if not parent_exists:
            raise ValueError(
                f"Parent table '{parent_table}' not found in schema 'public'"
            )

        await conn.execute(
            text(
                f"ALTER TABLE {q_parent} ADD COLUMN IF NOT EXISTS subcategory_id BIGINT"
            )
        )

        parent_insert = await conn.execute(
            text(
                f"""
                INSERT INTO {q_parent} (name, subcategory_id)
                VALUES (:name, NULL)
                RETURNING id
                """
            ),
            {"name": child_table_name},
        )
        parent_record_id = parent_insert.scalar_one()

        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {q_child} (
                    id BIGSERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    subcategory_id BIGINT
                )
                """
            )
        )

        child_insert = await conn.execute(
            text(
                f"""
                INSERT INTO {q_child} (name, subcategory_id)
                VALUES (:name, NULL)
                RETURNING id
                """
            ),
            {"name": child_table_name},
        )
        child_record_id = child_insert.scalar_one()

        await conn.execute(
            text(
                f"""
                UPDATE {q_parent}
                SET subcategory_id = :child_record_id
                WHERE id = :parent_record_id
                """
            ),
            {
                "child_record_id": child_record_id,
                "parent_record_id": parent_record_id,
            },
        )

    return {
        "table_name": child_table_name,
        "parent_table_name": parent_table,
        "parent_record_id": int(parent_record_id),
        "child_record_id": int(child_record_id),
    }


async def create_product_leaf(
    product_table_name: str,
    category_table_name: str,
    category_id: int,
    product_name: str,
    price: float,
    quantity: int,
) -> dict[str, int | str | float]:
    if category_id <= 0:
        raise ValueError("category_id must be greater than 0")
    if quantity < 0:
        raise ValueError("quantity must be greater than or equal to 0")
    if price < 0:
        raise ValueError("price must be greater than or equal to 0")

    clean_product_name = product_name.strip()
    if not clean_product_name:
        raise ValueError("product_name is required")

    product_table = normalize_table_name(product_table_name)
    category_table = normalize_table_name(category_table_name)
    q_product = quote_table_name(product_table)
    q_category = quote_table_name(category_table)

    engine = get_engine()
    async with engine.begin() as conn:
        category_table_exists = await conn.scalar(
            text(
                """
                SELECT EXISTS(
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
                """
            ),
            {"table_name": category_table},
        )
        if not category_table_exists:
            raise ValueError(
                f"Category table '{category_table}' not found in schema 'public'"
            )

        category_exists = await conn.scalar(
            text(
                f"""
                SELECT EXISTS(
                    SELECT 1
                    FROM {q_category}
                    WHERE id = :category_id
                )
                """
            ),
            {"category_id": category_id},
        )
        if not category_exists:
            raise ValueError(
                f"Category with id={category_id} not found in table '{category_table}'"
            )

        await conn.execute(
            text(
                f"""
                CREATE TABLE IF NOT EXISTS {q_product} (
                    id BIGSERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    price NUMERIC(14, 2) NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    category_table_name VARCHAR(255) NOT NULL,
                    category_id BIGINT NOT NULL
                )
                """
            )
        )

        insert_result = await conn.execute(
            text(
                f"""
                INSERT INTO {q_product}
                    (name, price, quantity, category_table_name, category_id)
                VALUES
                    (:name, :price, :quantity, :category_table_name, :category_id)
                RETURNING id
                """
            ),
            {
                "name": clean_product_name,
                "price": price,
                "quantity": quantity,
                "category_table_name": category_table,
                "category_id": category_id,
            },
        )
        product_id = insert_result.scalar_one()

        await conn.execute(
            text(
                f"ALTER TABLE {q_category} ADD COLUMN IF NOT EXISTS subcategory_id BIGINT"
            )
        )
        await conn.execute(
            text(
                f"""
                UPDATE {q_category}
                SET subcategory_id = :subcategory_id
                WHERE id = :category_id
                """
            ),
            {"subcategory_id": product_id, "category_id": category_id},
        )

    return {
        "product_table_name": product_table,
        "category_table_name": category_table,
        "category_id": int(category_id),
        "product_id": int(product_id),
        "name": clean_product_name,
        "price": float(price),
        "quantity": int(quantity),
    }


async def close_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
