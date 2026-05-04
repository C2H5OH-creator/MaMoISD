from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from src.api.models import (
    CategoryCreateRequest,
    CategoryMoveRequest,
    CategoryResponse,
    CategoryUpdateRequest,
    DatabaseInfoResponse,
    EnumerationCreateRequest,
    EnumerationDetailResponse,
    EnumerationResponse,
    EnumerationUpdateRequest,
    EnumerationValueCreateRequest,
    EnumerationValueResponse,
    EnumerationValueUpdateRequest,
    MeasurementUnitCreateRequest,
    MeasurementUnitResponse,
    MeasurementUnitUpdateRequest,
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
    create_enumeration,
    create_enumeration_value,
    create_measurement_unit,
    create_product,
    create_tables,
    delete_category,
    delete_enumeration,
    delete_enumeration_value,
    delete_measurement_unit,
    delete_product,
    get_category,
    get_database_summary,
    get_enumeration,
    get_measurement_unit,
    get_postgres_creds,
    get_product,
    get_tree,
    list_categories,
    list_enumeration_values,
    list_enumerations,
    list_measurement_units,
    list_products,
    list_specifications,
    move_category,
    move_product,
    update_category,
    update_enumeration,
    update_enumeration_value,
    update_measurement_unit,
    update_product,
)

router = APIRouter(prefix="/database")

service_router = APIRouter(tags=["database-service"])
specifications_router = APIRouter(tags=["database-specifications"])
measurement_units_router = APIRouter(tags=["database-measurement-units"])
categories_router = APIRouter(tags=["database-categories"])
products_router = APIRouter(tags=["database-products"])
enumerations_router = APIRouter(tags=["database-enumerations"])


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
            continue
        item: dict[str, object] = {"name": spec.name}
        if spec.enum_value_id is not None:
            item["enum_value_id"] = spec.enum_value_id
        else:
            item["value"] = spec.value
            if spec.unit_id is not None:
                item["unit_id"] = spec.unit_id
            elif spec.custom_unit_full_name is not None and spec.custom_unit_short_name is not None:
                item["custom_unit_full_name"] = spec.custom_unit_full_name
                item["custom_unit_short_name"] = spec.custom_unit_short_name
        payload.append(item)
    return payload


@service_router.get(
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


@service_router.post(
    "/tables/create",
    response_model=MessageResponse,
    summary="Создать таблицы БД",
    description="Создает фиксированную схему: categories, products, specifications, measurement_units, enumerations.",
)
async def create_tables_endpoint() -> MessageResponse:
    await create_tables()
    return MessageResponse(
        message="Таблицы categories, products, specifications, measurement_units, enumerations и enumeration_values готовы"
    )


@service_router.get(
    "/tree",
    summary="Получить дерево классификатора",
    description="Возвращает корень, все категории и конечные комплектующие целиком.",
)
async def get_tree_endpoint() -> dict[str, object]:
    return await get_tree()


@specifications_router.get(
    "/specifications",
    response_model=list[SpecificationResponse],
    summary="Справочник спецификаций",
    description="Возвращает уникальные спецификации, которые можно переиспользовать по id.",
)
async def list_specifications_endpoint() -> list[SpecificationResponse]:
    specifications = await list_specifications()
    return [SpecificationResponse(**specification) for specification in specifications]


@measurement_units_router.get(
    "/measurement-units",
    response_model=list[MeasurementUnitResponse],
    summary="Справочник единиц измерения",
)
async def list_measurement_units_endpoint() -> list[MeasurementUnitResponse]:
    units = await list_measurement_units()
    return [MeasurementUnitResponse(**unit) for unit in units]


@measurement_units_router.post(
    "/measurement-units",
    response_model=MeasurementUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать единицу измерения",
)
async def create_measurement_unit_endpoint(
    payload: MeasurementUnitCreateRequest,
) -> MeasurementUnitResponse:
    try:
        unit = await create_measurement_unit(
            full_name=payload.full_name,
            short_name=payload.short_name,
            description=payload.description,
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return MeasurementUnitResponse(**unit)


@measurement_units_router.get(
    "/measurement-units/{unit_id}",
    response_model=MeasurementUnitResponse,
    summary="Получить единицу измерения",
)
async def get_measurement_unit_endpoint(unit_id: int) -> MeasurementUnitResponse:
    try:
        unit = await get_measurement_unit(unit_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return MeasurementUnitResponse(**unit)


@measurement_units_router.patch(
    "/measurement-units/{unit_id}",
    response_model=MeasurementUnitResponse,
    summary="Изменить единицу измерения",
)
async def update_measurement_unit_endpoint(
    unit_id: int,
    payload: MeasurementUnitUpdateRequest,
) -> MeasurementUnitResponse:
    try:
        unit = await update_measurement_unit(
            unit_id,
            full_name=payload.full_name,
            short_name=payload.short_name,
            description=payload.description,
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return MeasurementUnitResponse(**unit)


@measurement_units_router.delete(
    "/measurement-units/{unit_id}",
    response_model=MessageResponse,
    summary="Удалить единицу измерения",
)
async def delete_measurement_unit_endpoint(unit_id: int) -> MessageResponse:
    try:
        await delete_measurement_unit(unit_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return MessageResponse(message=f"Единица измерения id={unit_id} удалена")


@categories_router.post(
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


@categories_router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="Получить список категорий",
)
async def list_categories_endpoint() -> list[CategoryResponse]:
    categories = await list_categories()
    return [CategoryResponse(**category) for category in categories]


@categories_router.get(
    "/categories/{category_id}",
    response_model=CategoryResponse,
    summary="Получить категорию",
)
async def get_category_endpoint(category_id: int) -> CategoryResponse:
    try:
        category = await get_category(category_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return CategoryResponse(**category)


@categories_router.patch(
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


@categories_router.patch(
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


@categories_router.delete(
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


@products_router.post(
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


@products_router.get(
    "/products",
    response_model=list[ProductResponse],
    summary="Получить список комплектующих",
)
async def list_products_endpoint() -> list[ProductResponse]:
    products = await list_products()
    return [ProductResponse(**product) for product in products]


@products_router.get(
    "/products/{product_id}",
    response_model=ProductResponse,
    summary="Получить комплектующее",
)
async def get_product_endpoint(product_id: int) -> ProductResponse:
    try:
        product = await get_product(product_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return ProductResponse(**product)


@products_router.patch(
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


@products_router.patch(
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


@products_router.delete(
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


@enumerations_router.get(
    "/enumerations",
    response_model=list[EnumerationResponse],
    summary="Получить список перечислений",
)
async def list_enumerations_endpoint() -> list[EnumerationResponse]:
    enumerations = await list_enumerations()
    return [EnumerationResponse(**enumeration) for enumeration in enumerations]


@enumerations_router.post(
    "/enumerations",
    response_model=EnumerationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Создать перечисление",
)
async def create_enumeration_endpoint(
    payload: EnumerationCreateRequest,
) -> EnumerationResponse:
    try:
        enumeration = await create_enumeration(
            name=payload.name,
            description=payload.description,
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return EnumerationResponse(**enumeration)


@enumerations_router.get(
    "/enumerations/{enumeration_id}",
    response_model=EnumerationDetailResponse,
    summary="Получить перечисление с его значениями",
)
async def get_enumeration_endpoint(enumeration_id: int) -> EnumerationDetailResponse:
    try:
        enumeration = await get_enumeration(enumeration_id)
        values = await list_enumeration_values(enumeration_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return EnumerationDetailResponse(
        **enumeration,
        values=[EnumerationValueResponse(**value) for value in values],
    )


@enumerations_router.patch(
    "/enumerations/{enumeration_id}",
    response_model=EnumerationResponse,
    summary="Изменить перечисление",
)
async def update_enumeration_endpoint(
    enumeration_id: int,
    payload: EnumerationUpdateRequest,
) -> EnumerationResponse:
    try:
        enumeration = await update_enumeration(
            enumeration_id,
            name=payload.name,
            description=payload.description,
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return EnumerationResponse(**enumeration)


@enumerations_router.delete(
    "/enumerations/{enumeration_id}",
    response_model=MessageResponse,
    summary="Удалить перечисление",
)
async def delete_enumeration_endpoint(enumeration_id: int) -> MessageResponse:
    try:
        await delete_enumeration(enumeration_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return MessageResponse(message=f"Перечисление id={enumeration_id} удалено")


@enumerations_router.get(
    "/enumerations/{enumeration_id}/values",
    response_model=list[EnumerationValueResponse],
    summary="Получить значения перечисления",
)
async def list_enumeration_values_endpoint(
    enumeration_id: int,
) -> list[EnumerationValueResponse]:
    try:
        values = await list_enumeration_values(enumeration_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return [EnumerationValueResponse(**value) for value in values]


@enumerations_router.post(
    "/enumerations/{enumeration_id}/values",
    response_model=EnumerationValueResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Добавить значение в перечисление",
)
async def create_enumeration_value_endpoint(
    enumeration_id: int,
    payload: EnumerationValueCreateRequest,
) -> EnumerationValueResponse:
    try:
        enumeration_value = await create_enumeration_value(
            enum_id=enumeration_id,
            item_type=payload.item_type,
            value=payload.value,
            child_enum_id=payload.child_enum_id,
            priority=payload.priority,
            description=payload.description,
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return EnumerationValueResponse(**enumeration_value)


@enumerations_router.patch(
    "/enumeration-values/{value_id}",
    response_model=EnumerationValueResponse,
    summary="Изменить значение перечисления",
)
async def update_enumeration_value_endpoint(
    value_id: int,
    payload: EnumerationValueUpdateRequest,
) -> EnumerationValueResponse:
    try:
        enumeration_value = await update_enumeration_value(
            value_id,
            item_type=payload.item_type,
            value=payload.value,
            child_enum_id=payload.child_enum_id,
            priority=payload.priority,
            description=payload.description,
        )
    except TreeError as exc:
        _raise_tree_error(exc)
    return EnumerationValueResponse(**enumeration_value)


@enumerations_router.delete(
    "/enumeration-values/{value_id}",
    response_model=MessageResponse,
    summary="Удалить значение перечисления",
)
async def delete_enumeration_value_endpoint(value_id: int) -> MessageResponse:
    try:
        await delete_enumeration_value(value_id)
    except TreeError as exc:
        _raise_tree_error(exc)
    return MessageResponse(message=f"Значение перечисления id={value_id} удалено")


router.include_router(service_router)
router.include_router(specifications_router)
router.include_router(measurement_units_router)
router.include_router(categories_router)
router.include_router(products_router)
router.include_router(enumerations_router)
