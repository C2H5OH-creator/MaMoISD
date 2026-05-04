# МиСПрИС API

REST API для классификатора комплектующих ПК и серверов на `FastAPI` и `PostgreSQL`.

## Что реализовано

- хранение дерева категорий в таблице `categories`;
- хранение конечных комплектующих в таблице `products`;
- хранение справочника уникальных характеристик в таблице `specifications`;
- хранение справочника единиц измерения в таблице `measurement_units`;
- хранение справочника параметров изделий в таблице `parameters`;
- хранение классификаторов в таблице `enumerations`;
- хранение значений классификаторов в таблице `enumeration_values`;
- связь many-to-many между товарами и характеристиками через `product_specifications`;
- создание, изменение, удаление и перемещение категорий;
- создание, изменение, удаление и перемещение товаров;
- создание, изменение, удаление перечислений и их значений;
- добавление одних перечислений внутрь других перечислений;
- получение полного дерева классификатора через API;
- переиспользование спецификаций по `id` или автоматическое создание новых;
- Swagger UI для тестирования запросов.

## Структура БД

Сервис использует фиксированную схему:

- `categories`
  хранит категории классификатора и ссылки на родительские категории;
- `products`
  хранит конечные комплектующие;
- `specifications`
  хранит уникальные характеристики в формате `name + value` или `name + enum_value_id`;
- `measurement_units`
  хранит единицы измерения: полное название, сокращенное название и описание;
- `parameters`
  хранит метаданные параметров изделий: код, название, тип, единицу измерения или перечисление;
- `category_parameters`
  хранит состав параметров классов изделий, порядок, обязательность и числовые ограничения;
- `product_parameter_values`
  хранит значения параметров конкретных изделий в отдельных полях по типам;
- `enumerations`
  хранит сами классификаторы;
- `enumeration_values`
  хранит конечные значения классификаторов и ссылки на вложенные перечисления;
- `product_specifications`
  хранит связи между товарами и характеристиками.

## Запуск

### Через Docker

```bash
docker compose up --build
```

После запуска будут доступны:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Локально

Нужен PostgreSQL с параметрами из `local_settings.py`.

Установка зависимостей:

```bash
pip install -r requirements.txt
```

Запуск:

```bash
uvicorn src.main:app --reload
```

## Основные эндпоинты

### Служебные

- `GET /info/ping` — проверка доступности API
- `GET /database/info` — краткая информация о БД
- `POST /database/tables/create` — явное создание таблиц и подготовка корня

### Категории

- `GET /database/categories` — получить список категорий
- `GET /database/categories/{category_id}` — получить категорию
- `POST /database/categories` — создать категорию
- `PATCH /database/categories/{category_id}` — переименовать категорию
- `PATCH /database/categories/{category_id}/move` — переместить категорию
- `DELETE /database/categories/{category_id}` — удалить категорию

Пример создания категории:

```json
{
  "name": "Процессоры для ПК",
  "parent_id": 2
}
```

Если `parent_id` не передан, категория создается под корнем.

### Товары

- `GET /database/products` — получить список товаров
- `GET /database/products/{product_id}` — получить товар
- `POST /database/products` — создать товар
- `PATCH /database/products/{product_id}` — изменить товар
- `PATCH /database/products/{product_id}/move` — переместить товар
- `DELETE /database/products/{product_id}` — удалить товар

Пример создания товара:

```json
{
  "category_id": 7,
  "name": "AMD Ryzen 7 5700X, AM4, OEM",
  "price": 14990,
  "quantity": 7,
  "description": "Процессор для ПК",
  "specifications": [
    { "name": "socket", "value": "AM4" },
    { "name": "form_factor", "value": "OEM" }
  ]
}
```

### Спецификации

- `GET /database/specifications` — получить справочник всех уникальных спецификаций

### Единицы измерения

- `GET /database/measurement-units` — получить список единиц измерения
- `POST /database/measurement-units` — создать единицу измерения
- `GET /database/measurement-units/{unit_id}` — получить единицу измерения
- `PATCH /database/measurement-units/{unit_id}` — изменить единицу измерения
- `DELETE /database/measurement-units/{unit_id}` — удалить единицу измерения

Пример создания единицы измерения:

```json
{
  "full_name": "нанометры",
  "short_name": "нм",
  "description": "Единица измерения длины"
}
```

### Параметры изделий

- `GET /database/parameters` — получить список параметров
- `POST /database/parameters` — создать параметр
- `GET /database/parameters/{parameter_id}` — получить параметр
- `PATCH /database/parameters/{parameter_id}` — изменить параметр
- `DELETE /database/parameters/{parameter_id}` — удалить параметр

Пример числового параметра:

```json
{
  "code": "tech_process",
  "name": "Техпроцесс",
  "description": "Технологический процесс производства",
  "parameter_type": "integer",
  "unit_id": 1,
  "enum_id": null
}
```

Пример параметра-перечисления:

```json
{
  "code": "socket",
  "name": "Сокет",
  "description": "Процессорный разъем",
  "parameter_type": "enum",
  "unit_id": null,
  "enum_id": 1
}
```

### Параметры категорий

- `GET /database/categories/{category_id}/parameters` — получить параметры категории
- `POST /database/categories/{category_id}/parameters` — назначить параметр категории
- `PATCH /database/category-parameters/{category_parameter_id}` — изменить настройки параметра категории
- `DELETE /database/category-parameters/{category_parameter_id}` — удалить параметр из категории
- `POST /database/categories/{category_id}/parameters/copy-from-parent` — скопировать параметры родителя

Пример назначения числового параметра категории:

```json
{
  "parameter_id": 1,
  "priority": 10,
  "is_required": true,
  "min_value": 1,
  "max_value": 100
}
```

### Значения параметров изделий

- `GET /database/products/{product_id}/parameters` — получить значения параметров изделия
- `PUT /database/products/{product_id}/parameters/{parameter_id}` — записать или обновить значение параметра изделия
- `DELETE /database/products/{product_id}/parameters/{parameter_id}` — удалить значение параметра изделия
- `GET /database/categories/{category_id}/products-with-parameters` — получить изделия категории со значениями параметров
- `POST /database/categories/{category_id}/products/search` — отфильтровать изделия категории по значениям параметров

Пример целочисленного значения:

```json
{
  "val_int": 8
}
```

Пример вещественного значения:

```json
{
  "val_real": 3.5
}
```

Пример значения-перечисления:

```json
{
  "enum_value_id": 1
}
```

Пример фильтрации по числовому параметру:

```json
{
  "filters": [
    {
      "parameter_id": 2,
      "operator": "gte",
      "val_int": 8
    }
  ]
}
```

Пример фильтрации по перечислению:

```json
{
  "filters": [
    {
      "parameter_id": 1,
      "operator": "eq",
      "enum_value_id": 3
    }
  ]
}
```

Пример ответа:

```json
[
  {
    "id": 1,
    "name": "tech_process",
    "value": "3",
    "enum_value_id": null,
    "unit_id": 1,
    "custom_unit_full_name": null,
    "custom_unit_short_name": null
  }
]
```

При создании или обновлении товара спецификацию можно передать тремя способами.

1. Как новую или переиспользуемую пару `name/value`:

```json
{
  "name": "socket",
  "value": "AM4"
}
```

Спецификация со ссылкой на единицу измерения из справочника:

```json
{
  "name": "tech_process",
  "value": "3",
  "unit_id": 1
}
```

Спецификация с частной единицей измерения, которая не добавляется в общий справочник:

```json
{
  "name": "custom_length",
  "value": "12",
  "custom_unit_full_name": "условные единицы",
  "custom_unit_short_name": "у.е."
}
```

2. Как новую или переиспользуемую пару `name/enum_value_id`, если значение берется из классификатора:

```json
{
  "name": "form_factor",
  "enum_value_id": 3
}
```

3. Как ссылку на уже существующую запись справочника:

```json
{
  "specification_id": 1
}
```

Пример товара с переиспользуемой спецификацией:

```json
{
  "category_id": 7,
  "name": "AMD Ryzen 9 7900",
  "price": 32000,
  "quantity": 4,
  "description": "Процессор для ПК",
  "specifications": [
    { "specification_id": 1 },
    { "name": "cores", "value": "12" },
    { "name": "form_factor", "enum_value_id": 3 }
  ]
}
```

### Перечисления

- `GET /database/enumerations` — получить список перечислений
- `POST /database/enumerations` — создать перечисление
- `GET /database/enumerations/{enumeration_id}` — получить перечисление вместе со значениями
- `PATCH /database/enumerations/{enumeration_id}` — изменить перечисление
- `DELETE /database/enumerations/{enumeration_id}` — удалить перечисление
- `GET /database/enumerations/{enumeration_id}/values` — получить значения перечисления
- `POST /database/enumerations/{enumeration_id}/values` — добавить конечное значение или вложенное перечисление
- `PATCH /database/enumeration-values/{value_id}` — изменить элемент перечисления
- `DELETE /database/enumeration-values/{value_id}` — удалить элемент перечисления

Пример создания перечисления:

```json
{
  "name": "Форматы материнских плат",
  "description": "Допустимые форм-факторы материнских плат"
}
```

Пример добавления значения в перечисление:

```json
{
  "item_type": "value",
  "value": "ATX",
  "priority": 10,
  "description": "Стандартный полноразмерный форм-фактор"
}
```

Пример добавления другого перечисления внутрь перечисления:

```json
{
  "item_type": "enum",
  "child_enum_id": 2,
  "priority": 20,
  "description": "Вложенный классификатор совместимых форм-факторов"
}
```

### Дерево классификатора

- `GET /database/tree` — получить все дерево целиком

В ответе возвращаются:

- корневая категория;
- все дочерние категории;
- все товары в соответствующих категориях;
- список спецификаций у каждого товара.

## Бизнес-ограничения

Сервис возвращает ошибку, если:

- указана несуществующая родительская категория;
- создается дублирующаяся категория на одном уровне дерева;
- создается дублирующийся товар в одной категории;
- удаляется несуществующая категория или товар;
- удаляется категория, в которой есть подкатегории или товары;
- категория переносится в саму себя или в собственного потомка;
- товар переносится в категорию, где уже есть товар с таким же именем;
- передан несуществующий `specification_id`;
- передан несуществующий `enum_value_id`;
- создается перечисление с уже существующим именем;
- создается дублирующееся значение внутри одного перечисления;
- перечисление добавляется внутрь самого себя;
- добавление вложенного перечисления создает цикл.

## Полезные файлы проекта

- [src/main.py](/home/c2h5oh/dev/projects/mispris/src/main.py) — запуск приложения
- [src/db/database.py](/home/c2h5oh/dev/projects/mispris/src/db/database.py) — схема БД и логика работы с данными
- [src/api/database.py](/home/c2h5oh/dev/projects/mispris/src/api/database.py) — HTTP-методы
- [src/api/models.py](/home/c2h5oh/dev/projects/mispris/src/api/models.py) — Pydantic-модели
- [docs/database_description.md](/home/c2h5oh/dev/projects/mispris/docs/database_description.md) — раздел про БД для отчета
- [docs/server_description.md](/home/c2h5oh/dev/projects/mispris/docs/server_description.md) — раздел про серверную часть
- [docs/conclusion.md](/home/c2h5oh/dev/projects/mispris/docs/conclusion.md) — заключение
- [docs/appendix_a.md](/home/c2h5oh/dev/projects/mispris/docs/appendix_a.md) — приложение А
