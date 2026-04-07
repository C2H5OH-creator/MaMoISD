from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from src.api.models import (
    CategoryCreateRequest,
    CategoryMoveRequest,
    CategoryResponse,
    CategoryUpdateRequest,
    DatabaseInfoResponse,
    MessageResponse,
    ProductCreateRequest,
    ProductMoveRequest,
    ProductResponse,
    ProductUpdateRequest,
    SpecificationResponse,
)
from src.db.database import (
    TreeError,
    create_category,
    create_product,
    create_tables,
    delete_category,
    delete_product,
    get_database_summary,
    get_postgres_creds,
    list_specifications,
    get_tree,
    move_category,
    move_product,
    update_category,
    update_product,
)

router = APIRouter(prefix="/database", tags=["database"])


def _raise_tree_error(exc: TreeError) -> None:
    detail = str(exc)
    lowered = detail.lower()
    if "не найден" in lowered:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _specs_payload(specifications) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for spec in specifications:
        if spec.specification_id is not None:
            payload.append({"specification_id": spec.specification_id})
        else:
            payload.append({"name": spec.name, "value": spec.value})
    return payload


@router.get(
    "/info",
    response_model=DatabaseInfoResponse,
    summary="Информация о БД",
)
async def get_database_info() -> DatabaseInfoResponse:
    creds = get_postgres_creds()
    summary = await get_database_summary()
    return DatabaseInfoResponse(
        status="ok",
        database=creds["database"],
        host=creds["host"],
        port=creds["port"],
        root_category_id=summary["root_category_id"],
        categories_count=summary["categories_count"],
        products_count=summary["products_count"],
        specifications_count=summary["specifications_count"],
    )


@router.post(
    "/tables/create",
    response_model=MessageResponse,
    summary="Создать таблицы БД",
    description="Создает фиксированную схему: categories, products, specifications.",
)
async def create_tables_endpoint() -> MessageResponse:
    await create_tables()
    return MessageResponse(message="Таблицы categories, products и specifications готовы")


@router.get(
    "/tree",
    summary="Получить дерево классификатора",
    description="Возвращает корень, все категории и конечные комплектующие целиком.",
)
async def get_tree_endpoint() -> dict[str, object]:
    return await get_tree()


@router.get(
    "/specifications",
    response_model=list[SpecificationResponse],
    summary="Справочник спецификаций",
    description="Возвращает уникальные спецификации, которые можно переиспользовать по id.",
)
async def list_specifications_endpoint() -> list[SpecificationResponse]:
    specifications = await list_specifications()
    return [SpecificationResponse(**specification) for specification in specifications]


@router.post(
    "/categories",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать категорию",
)
async def create_category_endpoint(payload: CategoryCreateRequest) -> CategoryResponse:
    try:
        category = await create_category(name=payload.name, parent_id=payload.parent_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return CategoryResponse(**category)


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Переименовать категорию",
)
async def update_category_endpoint(
    category_id: int,
    payload: CategoryUpdateRequest,
) -> CategoryResponse:
    try:
        category = await update_category(category_id, name=payload.name)
    except TreeError as exc:
        _raise_tree_error(exc)
    return CategoryResponse(**category)


@router.patch(
    "/categories/{category_id}/move",
    response_model=CategoryResponse,
    summary="Переместить категорию",
)
async def move_category_endpoint(
    category_id: int,
    payload: CategoryMoveRequest,
) -> CategoryResponse:
    try:
        category = await move_category(category_id, payload.new_parent_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return CategoryResponse(**category)


@router.delete(
    "/categories/{category_id}",
    response_model=MessageResponse,
    summary="Удалить категорию",
)
async def delete_category_endpoint(category_id: int) -> MessageResponse:
    try:
        await delete_category(category_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return MessageResponse(message=f"Категория id={category_id} удалена")


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать комплектующее",
)
async def create_product_endpoint(payload: ProductCreateRequest) -> ProductResponse:
    try:
        product = await create_product(
            category_id=payload.category_id,
            name=payload.name,
            price=_to_decimal(payload.price),
            quantity=payload.quantity,
            description=payload.description,
            specifications=_specs_payload(payload.specifications),
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return ProductResponse(**product)


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Изменить комплектующее",
)
async def update_product_endpoint(
    product_id: int,
    payload: ProductUpdateRequest,
) -> ProductResponse:
    try:
        product = await update_product(
            product_id,
            name=payload.name,
            price=_to_decimal(payload.price),
            quantity=payload.quantity,
            description=payload.description,
            specifications=_specs_payload(payload.specifications),
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return ProductResponse(**product)


@router.patch(
    "/products/{product_id}/move",
    response_model=ProductResponse,
    summary="Переместить комплектующее в другую категорию",
)
async def move_product_endpoint(
    product_id: int,
    payload: ProductMoveRequest,
) -> ProductResponse:
    try:
        product = await move_product(product_id, payload.new_category_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return ProductResponse(**product)


@router.delete(
    "/products/{product_id}",
    response_model=MessageResponse,
    summary="Удалить комплектующее",
)
async def delete_product_endpoint(product_id: int) -> MessageResponse:
    try:
        await delete_product(product_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return MessageResponse(message=f"Комплектующее id={product_id} удалено")
