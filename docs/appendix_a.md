# ПРИЛОЖЕНИЕ А

## Листинг основных фрагментов исходного кода

### A.1 Инициализация серверного приложения

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api import api_router
from src.db.database import close_engine, create_global_database, create_tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_global_database()
    await create_tables()
    try:
        yield
    finally:
        await close_engine()


app = FastAPI(title="МиСПрИС API", lifespan=lifespan)
app.include_router(api_router)
```

### A.2 Подключение маршрутов API

```python
from fastapi import APIRouter

from src.api.database import router as database_router
from src.api.info import router as info_router

api_router = APIRouter()
api_router.include_router(info_router)
api_router.include_router(database_router)
```

### A.3 Модели запросов и ответов API

```python
from pydantic import BaseModel, Field, model_validator, field_validator


class MessageResponse(BaseModel):
    status: str = Field(default="ok", examples=["ok"])
    message: str


class SpecificationPayload(BaseModel):
    specification_id: int | None = Field(default=None, gt=0)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    value: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("name", "value")
    @classmethod
    def validate_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Поле не должно быть пустым")
        return normalized

    @model_validator(mode="after")
    def validate_payload(self):
        if self.specification_id is not None:
            if self.name is not None or self.value is not None:
                raise ValueError(
                    "Нужно передавать либо specification_id, либо name/value"
                )
            return self

        if self.name is None or self.value is None:
            raise ValueError(
                "Для новой спецификации нужно передать оба поля: name и value"
            )
        return self


class SpecificationResponse(BaseModel):
    id: int
    name: str
    value: str


class CategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: int | None = Field(default=None, gt=0)


class CategoryUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class CategoryMoveRequest(BaseModel):
    new_parent_id: int = Field(gt=0)


class CategoryResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None


class ProductBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: float = Field(ge=0)
    quantity: int = Field(ge=0)
    description: str | None = Field(default=None, max_length=1000)
    specifications: list[SpecificationPayload] = Field(default_factory=list)


class ProductCreateRequest(ProductBaseRequest):
    category_id: int = Field(gt=0)


class ProductUpdateRequest(ProductBaseRequest):
    pass


class ProductMoveRequest(BaseModel):
    new_category_id: int = Field(gt=0)


class ProductResponse(BaseModel):
    id: int
    name: str
    category_id: int
    price: float
    quantity: int
    description: str | None
    specifications: list[SpecificationResponse]
```

### A.4 Основные таблицы базы данных

```python
from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

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

specifications_table = Table(
    "specifications",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("product_id", Integer, ForeignKey("products.id", ondelete="CASCADE")),
    Column("name", String(255), nullable=False),
    Column("value", String(1000), nullable=False),
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
```

### A.5 Создание таблиц и подготовка корневой категории

```python
ROOT_CATEGORY_NAME = "Комплектующие ПК и серверов"


async def create_tables() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    async with get_session_factory()() as session:
        await ensure_root_category(session)
        await prepare_specifications_schema(session)
        await migrate_legacy_specifications(session)
        await session.commit()


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
```

### A.6 Операции над категориями классификатора

```python
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
        return {
            "id": int(row.id),
            "name": str(row.name),
            "parent_id": int(row.parent_id) if row.parent_id is not None else None,
        }


async def move_category(category_id: int, new_parent_id: int) -> dict[str, object]:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Нельзя переместить вершину: категория с id={category_id} не найдена")

        parent = await _get_category_row(session, new_parent_id)
        if parent is None:
            raise TreeError(
                f"Нельзя переместить вершину: новая родительская категория с id={new_parent_id} не найдена"
            )

        result = await session.execute(
            update(categories_table)
            .where(categories_table.c.id == category_id)
            .values(parent_id=new_parent_id)
            .returning(categories_table)
        )
        await session.commit()
        row = result.mappings().one()
        return {
            "id": int(row.id),
            "name": str(row.name),
            "parent_id": int(row.parent_id) if row.parent_id is not None else None,
        }


async def delete_category(category_id: int) -> None:
    async with get_session_factory()() as session:
        category = await _get_category_row(session, category_id)
        if category is None:
            raise TreeError(f"Нельзя удалить вершину: категория с id={category_id} не найдена")

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
```

### A.7 Операции над товарами и спецификациями

```python
async def _get_or_create_canonical_specification(
    session: AsyncSession,
    *,
    name: str,
    value: str,
) -> dict[str, object]:
    canonical_id = await session.scalar(
        select(specifications_table.c.id).where(
            specifications_table.c.product_id.is_(None),
            func.lower(specifications_table.c.name) == name.lower(),
            specifications_table.c.value == value,
        )
    )
    if canonical_id is None:
        result = await session.execute(
            insert(specifications_table)
            .values(name=name.strip(), value=value.strip(), product_id=None)
            .returning(specifications_table)
        )
        row = result.mappings().one()
        return {
            "id": int(row.id),
            "name": str(row.name),
            "value": str(row.value),
        }

    row = await _get_specification_row(session, int(canonical_id))
    return {
        "id": int(row.id),
        "name": str(row.name),
        "value": str(row.value),
    }


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


async def list_specifications() -> list[dict[str, object]]:
    async with get_session_factory()() as session:
        result = await session.execute(
            select(specifications_table)
            .where(specifications_table.c.product_id.is_(None))
            .order_by(specifications_table.c.name, specifications_table.c.value)
        )
        return [
            {
                "id": int(row.id),
                "name": str(row.name),
                "value": str(row.value),
            }
            for row in result.mappings().all()
        ]
```

### A.8 Построение полного дерева классификатора

```python
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
                "value": str(row["value"]),
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
                "price": float(row["price"]),
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

    return root_node
```

### A.9 Реализация HTTP-методов

```python
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

router = APIRouter(prefix="/database", tags=["database"])


def _raise_tree_error(exc: TreeError) -> None:
    detail = str(exc)
    lowered = detail.lower()
    if "не найден" in lowered:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


@router.get("/database/info")
async def get_database_info() -> DatabaseInfoResponse:
    ...


@router.post("/database/tables/create")
async def create_tables_endpoint() -> MessageResponse:
    ...


@router.get("/database/tree")
async def get_tree_endpoint() -> dict[str, object]:
    ...


@router.get("/database/specifications")
async def list_specifications_endpoint() -> list[SpecificationResponse]:
    ...


@router.post("/database/categories")
async def create_category_endpoint(payload: CategoryCreateRequest) -> CategoryResponse:
    ...


@router.patch("/database/categories/{category_id}")
async def update_category_endpoint(
    category_id: int,
    payload: CategoryUpdateRequest,
) -> CategoryResponse:
    ...


@router.patch("/database/categories/{category_id}/move")
async def move_category_endpoint(
    category_id: int,
    payload: CategoryMoveRequest,
) -> CategoryResponse:
    ...


@router.delete("/database/categories/{category_id}")
async def delete_category_endpoint(category_id: int) -> MessageResponse:
    ...


@router.post("/database/products")
async def create_product_endpoint(payload: ProductCreateRequest) -> ProductResponse:
    ...


@router.patch("/database/products/{product_id}")
async def update_product_endpoint(
    product_id: int,
    payload: ProductUpdateRequest,
) -> ProductResponse:
    ...


@router.patch("/database/products/{product_id}/move")
async def move_product_endpoint(
    product_id: int,
    payload: ProductMoveRequest,
) -> ProductResponse:
    ...


@router.delete("/database/products/{product_id}")
async def delete_product_endpoint(product_id: int) -> MessageResponse:
    ...
```

### A.10 Проверочный маршрут

```python
from fastapi import APIRouter

router = APIRouter(prefix="/info", tags=["info"])


@router.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "pong"}
```
