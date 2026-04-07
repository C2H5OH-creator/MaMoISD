from pydantic import BaseModel, Field, model_validator, field_validator


class MessageResponse(BaseModel):
    status: str = Field(default="ok", examples=["ok"])
    message: str


class SpecificationPayload(BaseModel):
    specification_id: int | None = Field(
        default=None,
        gt=0,
        examples=[1],
        description="ID уже существующей спецификации из справочника.",
    )
    name: str | None = Field(default=None, min_length=1, max_length=255, examples=["socket"])
    value: str | None = Field(default=None, min_length=1, max_length=1000, examples=["AM5"])

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
    name: str = Field(min_length=1, max_length=255, examples=["Процессоры"])
    parent_id: int | None = Field(
        default=None,
        gt=0,
        description="Если не указан, категория будет создана под корнем.",
        examples=[1],
    )

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Имя категории не должно быть пустым")
        return normalized


class CategoryUpdateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["Серверные процессоры"])

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Имя категории не должно быть пустым")
        return normalized


class CategoryMoveRequest(BaseModel):
    new_parent_id: int = Field(gt=0, examples=[2])


class CategoryResponse(BaseModel):
    id: int
    name: str
    parent_id: int | None


class ProductBaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255, examples=["AMD Ryzen 7 5700X"])
    price: float = Field(ge=0, examples=[14990.0])
    quantity: int = Field(ge=0, examples=[7])
    description: str | None = Field(
        default=None,
        max_length=1000,
        examples=["8 ядер, 16 потоков"],
    )
    specifications: list[SpecificationPayload] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Имя комплектующего не должно быть пустым")
        return normalized

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProductCreateRequest(ProductBaseRequest):
    category_id: int = Field(gt=0, examples=[3])


class ProductUpdateRequest(ProductBaseRequest):
    pass


class ProductMoveRequest(BaseModel):
    new_category_id: int = Field(gt=0, examples=[4])


class ProductResponse(BaseModel):
    id: int
    name: str
    category_id: int
    price: float
    quantity: int
    description: str | None
    specifications: list[SpecificationResponse]


class DatabaseInfoResponse(BaseModel):
    status: str
    database: str
    host: str
    port: str
    root_category_id: int
    categories_count: int
    products_count: int
    specifications_count: int
