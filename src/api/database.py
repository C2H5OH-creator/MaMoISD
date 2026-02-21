from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from src.api.models import (
    CreateTablesRequest,
    CreateTablesResponse,
    ProductCreateRequest,
    ProductCreateResponse,
    SubcategoryCreateRequest,
    SubcategoryCreateResponse,
)
from src.db.database import (
    create_category_tables,
    create_product_leaf,
    create_subcategory_table,
    get_engine,
    get_postgres_creds,
    normalize_table_name,
    quote_table_name,
)

router = APIRouter(prefix="/database", tags=["database"])


@router.get("/info")
async def get_database_info() -> dict[str, object]:
    creds = get_postgres_creds()
    engine = get_engine()

    async with engine.connect() as conn:
        db_name = await conn.scalar(text("SELECT current_database()"))
        categories_exists = await conn.scalar(
            text("SELECT to_regclass('public.categories') IS NOT NULL")
        )
        categories_count = None
        if categories_exists:
            categories_count = await conn.scalar(
                text("SELECT COUNT(*) FROM categories")
            )
        tables_result = await conn.execute(
            text(
                """
                SELECT
                    t.tablename AS table_name,
                    COALESCE(s.n_live_tup, 0)::bigint AS estimated_rows
                FROM pg_tables t
                LEFT JOIN pg_stat_user_tables s
                    ON s.schemaname = t.schemaname
                   AND s.relname = t.tablename
                WHERE t.schemaname = 'public'
                ORDER BY t.tablename
                """
            )
        )
        all_tables = [
            {"name": row.table_name, "estimated_rows": int(row.estimated_rows)}
            for row in tables_result
        ]

    return {
        "status": "ok",
        "database": db_name,
        "host": creds["host"],
        "port": creds["port"],
        "tables": {
            "categories_exists": bool(categories_exists),
            "categories_count": int(categories_count)
            if categories_count is not None
            else 0,
        },
        "all_tables": all_tables,
    }


@router.get(
    "/tables/{table_name}",
    summary="Информация о таблице",
    description=(
        "Возвращает краткую информацию по таблице: колонки, типы, PK, "
        "примерное число строк и срез записей по диапазону start..end."
    ),
)
async def get_table_info(
    table_name: str,
    start: int = Query(default=0, ge=0, description="Начало диапазона (включительно)."),
    end: int = Query(
        default=10, ge=1, description="Конец диапазона (не включительно)."
    ),
) -> dict[str, object]:
    engine = get_engine()
    try:
        normalized_table_name = normalize_table_name(table_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if end <= start:
        raise HTTPException(
            status_code=400,
            detail="end must be greater than start",
        )

    async with engine.connect() as conn:
        exists = await conn.scalar(
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
            {"table_name": normalized_table_name},
        )
        if not exists:
            raise HTTPException(
                status_code=404,
                detail=f"Table '{normalized_table_name}' not found in schema 'public'",
            )

        columns_result = await conn.execute(
            text(
                """
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    COALESCE(
                        EXISTS(
                            SELECT 1
                            FROM information_schema.table_constraints tc
                            JOIN information_schema.key_column_usage kcu
                              ON tc.constraint_name = kcu.constraint_name
                             AND tc.table_schema = kcu.table_schema
                            WHERE tc.constraint_type = 'PRIMARY KEY'
                              AND tc.table_schema = c.table_schema
                              AND tc.table_name = c.table_name
                              AND kcu.column_name = c.column_name
                        ),
                        FALSE
                    ) AS is_primary_key
                FROM information_schema.columns c
                WHERE c.table_schema = 'public'
                  AND c.table_name = :table_name
                ORDER BY c.ordinal_position
                """
            ),
            {"table_name": normalized_table_name},
        )
        columns = [
            {
                "name": row.column_name,
                "type": row.data_type,
                "nullable": row.is_nullable == "YES",
                "is_primary_key": bool(row.is_primary_key),
            }
            for row in columns_result
        ]

        estimated_rows = await conn.scalar(
            text(
                """
                SELECT COALESCE(n_live_tup, 0)::bigint
                FROM pg_stat_user_tables
                WHERE schemaname = 'public'
                  AND relname = :table_name
                """
            ),
            {"table_name": normalized_table_name},
        )

        limit = end - start
        q_table = quote_table_name(normalized_table_name)
        records_result = await conn.execute(
            text(
                f"""
                SELECT *
                FROM {q_table}
                OFFSET :start
                LIMIT :limit
                """
            ),
            {"start": start, "limit": limit},
        )
        records = [dict(row._mapping) for row in records_result]

    return {
        "status": "ok",
        "table": normalized_table_name,
        "schema": "public",
        "estimated_rows": int(estimated_rows or 0),
        "columns": columns,
        "range": {"start": start, "end": end},
        "records": records,
    }


@router.post(
    "/tables/create",
    response_model=CreateTablesResponse,
    summary="Создать таблицы БД",
    description="Создает необходимые таблицы для категорий, если они отсутствуют.",
)
async def create_tables(payload: CreateTablesRequest) -> CreateTablesResponse:
    if not payload.include_categories:
        raise HTTPException(
            status_code=400,
            detail="At least one table group must be enabled for creation",
        )
    await create_category_tables()
    return CreateTablesResponse(
        status="ok",
        message="Tables created (or already exist)",
    )


@router.post(
    "/subcategories",
    response_model=SubcategoryCreateResponse,
    summary="Создать таблицу-подкатегорию",
    description=(
        "Принимает имя новой таблицы и имя родительской таблицы. "
        "Создает запись в родительской таблице, затем создает новую таблицу "
        "и привязывает ее через поле subcategory_id в созданной родительской записи."
    ),
)
async def create_subcategory_endpoint(
    payload: SubcategoryCreateRequest,
) -> SubcategoryCreateResponse:
    try:
        result = await create_subcategory_table(
            table_name=payload.table_name,
            parent_table_name=payload.parent_table_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SubcategoryCreateResponse(
        status="ok",
        table_name=result["table_name"],
        parent_table_name=result["parent_table_name"],
        parent_record_id=result["parent_record_id"],
        child_record_id=result["child_record_id"],
    )


@router.post(
    "/products",
    response_model=ProductCreateResponse,
    summary="Создать товар в листовой таблице",
    description=(
        "Создает/использует таблицу товаров (лист дерева), добавляет в нее товар "
        "и привязывает запись к категории через category_table_name + category_id."
    ),
)
async def create_product_endpoint(
    payload: ProductCreateRequest,
) -> ProductCreateResponse:
    try:
        result = await create_product_leaf(
            product_table_name=payload.product_table_name,
            category_table_name=payload.category_table_name,
            category_id=payload.category_id,
            product_name=payload.name,
            price=payload.price,
            quantity=payload.quantity,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ProductCreateResponse(
        status="ok",
        product_table_name=result["product_table_name"],
        category_table_name=result["category_table_name"],
        category_id=result["category_id"],
        product_id=result["product_id"],
        name=result["name"],
        price=result["price"],
        quantity=result["quantity"],
    )
