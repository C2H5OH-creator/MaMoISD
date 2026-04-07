# МиСПрИС API

REST API для классификатора комплектующих ПК и серверов на `FastAPI` и `PostgreSQL`.

## Что реализовано

- хранение дерева категорий в таблице `categories`;
- хранение конечных комплектующих в таблице `products`;
- хранение справочника уникальных характеристик в таблице `specifications`;
- связь many-to-many между товарами и характеристиками через `product_specifications`;
- создание, изменение, удаление и перемещение категорий;
- создание, изменение, удаление и перемещение товаров;
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
  хранит уникальные пары `name/value`;
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

Пример ответа:

```json
[
  { "id": 1, "name": "socket", "value": "AM4" },
  { "id": 2, "name": "memory_type", "value": "DDR4" }
]
```

При создании или обновлении товара спецификацию можно передать двумя способами.

1. Как новую или переиспользуемую пару `name/value`:

```json
{
  "name": "socket",
  "value": "AM4"
}
```

2. Как ссылку на уже существующую запись справочника:

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
    { "name": "cores", "value": "12" }
  ]
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
- передан несуществующий `specification_id`.

## Полезные файлы проекта

- [src/main.py](/home/c2h5oh/dev/projects/mispris/src/main.py) — запуск приложения
- [src/db/database.py](/home/c2h5oh/dev/projects/mispris/src/db/database.py) — схема БД и логика работы с данными
- [src/api/database.py](/home/c2h5oh/dev/projects/mispris/src/api/database.py) — HTTP-методы
- [src/api/models.py](/home/c2h5oh/dev/projects/mispris/src/api/models.py) — Pydantic-модели
- [docs/database_description.md](/home/c2h5oh/dev/projects/mispris/docs/database_description.md) — раздел про БД для отчета
- [docs/server_description.md](/home/c2h5oh/dev/projects/mispris/docs/server_description.md) — раздел про серверную часть
- [docs/conclusion.md](/home/c2h5oh/dev/projects/mispris/docs/conclusion.md) — заключение
- [docs/appendix_a.md](/home/c2h5oh/dev/projects/mispris/docs/appendix_a.md) — приложение А
