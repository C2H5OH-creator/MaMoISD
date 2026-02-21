from pydantic import BaseModel, Field


class CreateTablesRequest(BaseModel):
    include_categories: bool = Field(
        default=True,
        description="Создать таблицу categories (иерархия категорий).",
        examples=[True],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "include_categories": True,
            }
        }
    }


class CreateTablesResponse(BaseModel):
    status: str = Field(description="Статус выполнения операции.", examples=["ok"])
    message: str = Field(
        description="Краткий результат операции.",
        examples=["Tables created (or already exist)"],
    )


class SubcategoryCreateRequest(BaseModel):
    table_name: str = Field(
        min_length=1,
        max_length=255,
        description="Имя таблицы, которую нужно создать как подкатегорию.",
        examples=["pc_windows"],
    )
    parent_table_name: str = Field(
        min_length=1,
        max_length=255,
        description="Имя родительской таблицы, к которой привязывается подкатегория.",
        examples=["categories"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "table_name": "pc_windows",
                "parent_table_name": "categories",
            }
        }
    }


class SubcategoryCreateResponse(BaseModel):
    status: str = Field(description="Статус выполнения операции.", examples=["ok"])
    table_name: str = Field(
        description="Имя созданной таблицы-подкатегории.", examples=["pc_windows"]
    )
    parent_table_name: str = Field(
        description="Имя родительской таблицы.", examples=["categories"]
    )
    parent_record_id: int = Field(
        description="ID записи, созданной в родительской таблице.", examples=[12]
    )
    child_record_id: int = Field(
        description="ID записи, созданной в таблице-подкатегории.", examples=[1]
    )


class ProductCreateRequest(BaseModel):
    product_table_name: str = Field(
        min_length=1,
        max_length=255,
        description="Имя листовой таблицы товаров (создается автоматически при отсутствии).",
        examples=["amd_products"],
    )
    category_table_name: str = Field(
        min_length=1,
        max_length=255,
        description="Имя таблицы категорий, где находится товар.",
        examples=["amd"],
    )
    category_id: int = Field(
        gt=0,
        description="ID категории (записи) в category_table_name.",
        examples=[3],
    )
    name: str = Field(
        min_length=1,
        max_length=255,
        description="Название товара.",
        examples=["AMD Ryzen 5 2600X"],
    )
    price: float = Field(
        ge=0,
        description="Цена товара.",
        examples=[14990.0],
    )
    quantity: int = Field(
        ge=0,
        description="Количество товара.",
        examples=[7],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "product_table_name": "amd_products",
                "category_table_name": "amd",
                "category_id": 3,
                "name": "AMD Ryzen 5 2600X",
                "price": 14990.0,
                "quantity": 7,
            }
        }
    }


class ProductCreateResponse(BaseModel):
    status: str = Field(description="Статус выполнения операции.", examples=["ok"])
    product_table_name: str = Field(
        description="Имя таблицы, где создан товар.", examples=["amd_products"]
    )
    category_table_name: str = Field(
        description="Имя таблицы категории.", examples=["amd"]
    )
    category_id: int = Field(description="ID категории.", examples=[3])
    product_id: int = Field(description="ID созданной записи товара.", examples=[11])
    name: str = Field(description="Название товара.", examples=["AMD Ryzen 5 2600X"])
    price: float = Field(description="Цена товара.", examples=[14990.0])
    quantity: int = Field(description="Количество товара.", examples=[7])
