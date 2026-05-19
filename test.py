# seed_localhost.py

import requests
from typing import Any

#BASE_URL = "http://localhost:8000/database"
BASE_URL = "http://mispris.c3h8o.ru/database"

def request(method: str, path: str, json: dict[str, Any] | None = None):
    url = f"{BASE_URL}{path}"
    response = requests.request(method, url, json=json)

    if response.status_code >= 400:
        print(f"[ERROR] {method} {path}")
        print(response.status_code, response.text)
        raise SystemExit(1)

    if response.text:
        return response.json()
    return None


def get_list(path: str) -> list[dict[str, Any]]:
    return request("GET", path)


def get_or_create_by_name(
    list_path: str,
    create_path: str,
    name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    items = get_list(list_path)

    for item in items:
        if item.get("name") == name:
            print(f"[SKIP] already exists: {name}")
            return item

    created = request("POST", create_path, payload)
    print(f"[CREATE] {name} -> id={created['id']}")
    return created


def get_or_create_unit(
    full_name: str,
    short_name: str,
    description: str | None = None,
) -> dict[str, Any]:
    items = get_list("/measurement-units")

    for item in items:
        if item["short_name"] == short_name or item["full_name"] == full_name:
            print(f"[SKIP] unit exists: {short_name}")
            return item

    created = request(
        "POST",
        "/measurement-units",
        {
            "full_name": full_name,
            "short_name": short_name,
            "description": description,
        },
    )
    print(f"[CREATE] unit {short_name} -> id={created['id']}")
    return created


def get_or_create_category(
    name: str,
    parent_id: int | None = None,
) -> dict[str, Any]:
    categories = get_list("/categories")

    for category in categories:
        if category["name"] == name and category["parent_id"] == parent_id:
            print(f"[SKIP] category exists: {name}")
            return category

    payload = {"name": name}
    if parent_id is not None:
        payload["parent_id"] = parent_id

    created = request("POST", "/categories", payload)
    print(f"[CREATE] category {name} -> id={created['id']}")
    return created


def get_or_create_enumeration(
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    return get_or_create_by_name(
        "/enumerations",
        "/enumerations",
        name,
        {
            "name": name,
            "description": description,
        },
    )


def get_or_create_enum_value(
    enum_id: int,
    value: str,
    priority: int = 0,
    description: str | None = None,
) -> dict[str, Any]:
    values = get_list(f"/enumerations/{enum_id}/values")

    for item in values:
        if item["item_type"] == "value" and item["value"] == value:
            print(f"[SKIP] enum value exists: {value}")
            return item

    created = request(
        "POST",
        f"/enumerations/{enum_id}/values",
        {
            "item_type": "value",
            "value": value,
            "child_enum_id": None,
            "priority": priority,
            "description": description,
        },
    )
    print(f"[CREATE] enum value {value} -> id={created['id']}")
    return created


def get_or_create_parameter(
    code: str,
    name: str,
    parameter_type: str,
    description: str | None = None,
    unit_id: int | None = None,
    enum_id: int | None = None,
) -> dict[str, Any]:
    parameters = get_list("/parameters")

    for parameter in parameters:
        if parameter["code"] == code:
            print(f"[SKIP] parameter exists: {code}")
            return parameter

    payload = {
        "code": code,
        "name": name,
        "description": description,
        "parameter_type": parameter_type,
        "unit_id": unit_id,
        "enum_id": enum_id,
    }

    created = request("POST", "/parameters", payload)
    print(f"[CREATE] parameter {code} -> id={created['id']}")
    return created


def assign_parameter_to_category(
    category_id: int,
    parameter_id: int,
    priority: int,
    is_required: bool = True,
    min_value: float | None = None,
    max_value: float | None = None,
) -> dict[str, Any]:
    current = get_list(f"/categories/{category_id}/parameters")

    for item in current:
        if item["parameter_id"] == parameter_id:
            print(
                f"[SKIP] category parameter exists: "
                f"category={category_id}, parameter={parameter_id}"
            )
            return item

    created = request(
        "POST",
        f"/categories/{category_id}/parameters",
        {
            "parameter_id": parameter_id,
            "priority": priority,
            "is_required": is_required,
            "min_value": min_value,
            "max_value": max_value,
        },
    )
    print(
        f"[CREATE] category parameter "
        f"category={category_id}, parameter={parameter_id}"
    )
    return created


def get_or_create_product(
    name: str,
    category_id: int,
    price: float,
    quantity: int,
    description: str | None = None,
    specifications: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    products = get_list("/products")

    for product in products:
        if product["name"] == name and product["category_id"] == category_id:
            print(f"[SKIP] product exists: {name}")
            return product

    created = request(
        "POST",
        "/products",
        {
            "name": name,
            "category_id": category_id,
            "price": price,
            "quantity": quantity,
            "description": description,
            "specifications": specifications or [],
        },
    )
    print(f"[CREATE] product {name} -> id={created['id']}")
    return created


def set_product_parameter(
    product_id: int,
    parameter_id: int,
    **value,
) -> dict[str, Any]:
    saved = request(
        "PUT",
        f"/products/{product_id}/parameters/{parameter_id}",
        value,
    )
    print(
        f"[SET] product={product_id}, parameter={parameter_id}, value={value}"
    )
    return saved


def main():
    print("[INIT] create tables")
    request("POST", "/tables/create")

    info = request("GET", "/info")
    root_id = info["root_category_id"]
    print(f"[INFO] root_category_id={root_id}")

    # 1. Units
    unit_ghz = get_or_create_unit("Гигагерц", "ГГц", "Частота процессора")
    unit_watt = get_or_create_unit("Ватт", "Вт", "Потребляемая мощность")
    unit_gb = get_or_create_unit("Гигабайт", "ГБ", "Объем памяти")
    unit_nm = get_or_create_unit("Нанометр", "нм", "Технологический процесс")

    # 2. Enumerations
    enum_cpu_vendor = get_or_create_enumeration(
        "Производитель процессора",
        "Допустимые производители CPU",
    )
    enum_gpu_memory = get_or_create_enumeration(
        "Тип видеопамяти",
        "Допустимые типы памяти видеокарт",
    )
    enum_socket = get_or_create_enumeration(
        "Сокет процессора",
        "Сокеты CPU",
    )

    # 3. Enumeration values
    amd = get_or_create_enum_value(enum_cpu_vendor["id"], "AMD", 10)
    intel = get_or_create_enum_value(enum_cpu_vendor["id"], "Intel", 20)

    gddr6 = get_or_create_enum_value(enum_gpu_memory["id"], "GDDR6", 10)
    gddr6x = get_or_create_enum_value(enum_gpu_memory["id"], "GDDR6X", 20)

    am5 = get_or_create_enum_value(enum_socket["id"], "AM5", 10)
    lga1700 = get_or_create_enum_value(enum_socket["id"], "LGA1700", 20)

    # 4. Categories
    cpu_category = get_or_create_category("Процессоры", root_id)
    gpu_category = get_or_create_category("Видеокарты", root_id)
    motherboard_category = get_or_create_category("Материнские платы", root_id)

    # 5. Parameters
    p_cpu_vendor = get_or_create_parameter(
        code="cpu_vendor",
        name="Производитель процессора",
        parameter_type="enum",
        enum_id=enum_cpu_vendor["id"],
    )

    p_socket = get_or_create_parameter(
        code="socket",
        name="Сокет",
        parameter_type="enum",
        enum_id=enum_socket["id"],
    )

    p_base_frequency = get_or_create_parameter(
        code="base_frequency",
        name="Базовая частота",
        parameter_type="real",
        unit_id=unit_ghz["id"],
    )

    p_tdp = get_or_create_parameter(
        code="tdp",
        name="TDP",
        parameter_type="integer",
        unit_id=unit_watt["id"],
    )

    p_tech_process = get_or_create_parameter(
        code="tech_process",
        name="Техпроцесс",
        parameter_type="integer",
        unit_id=unit_nm["id"],
    )

    p_gpu_memory_type = get_or_create_parameter(
        code="gpu_memory_type",
        name="Тип видеопамяти",
        parameter_type="enum",
        enum_id=enum_gpu_memory["id"],
    )

    p_gpu_memory_size = get_or_create_parameter(
        code="gpu_memory_size",
        name="Объем видеопамяти",
        parameter_type="integer",
        unit_id=unit_gb["id"],
    )

    # 6. Category parameters
    assign_parameter_to_category(cpu_category["id"], p_cpu_vendor["id"], 10)
    assign_parameter_to_category(cpu_category["id"], p_socket["id"], 20)
    assign_parameter_to_category(
        cpu_category["id"],
        p_base_frequency["id"],
        30,
        min_value=1.0,
        max_value=8.0,
    )
    assign_parameter_to_category(
        cpu_category["id"],
        p_tdp["id"],
        40,
        min_value=1,
        max_value=300,
    )
    assign_parameter_to_category(
        cpu_category["id"],
        p_tech_process["id"],
        50,
        min_value=1,
        max_value=100,
    )

    assign_parameter_to_category(gpu_category["id"], p_gpu_memory_type["id"], 10)
    assign_parameter_to_category(
        gpu_category["id"],
        p_gpu_memory_size["id"],
        20,
        min_value=1,
        max_value=128,
    )
    assign_parameter_to_category(
        gpu_category["id"],
        p_tdp["id"],
        30,
        min_value=1,
        max_value=600,
    )

    # 7. Products
    ryzen_7600x = get_or_create_product(
        name="AMD Ryzen 5 7600X",
        category_id=cpu_category["id"],
        price=25990.00,
        quantity=12,
        description="6 ядер, 12 потоков, архитектура Zen 4",
        specifications=[
            {"name": "Количество ядер", "value": "6"},
            {"name": "Количество потоков", "value": "12"},
            {"name": "Сокет", "enum_value_id": am5["id"]},
        ],
    )

    intel_13600k = get_or_create_product(
        name="Intel Core i5-13600K",
        category_id=cpu_category["id"],
        price=31990.00,
        quantity=8,
        description="14 ядер, 20 потоков, Raptor Lake",
        specifications=[
            {"name": "Количество ядер", "value": "14"},
            {"name": "Количество потоков", "value": "20"},
            {"name": "Сокет", "enum_value_id": lga1700["id"]},
        ],
    )

    rtx_4070 = get_or_create_product(
        name="NVIDIA GeForce RTX 4070",
        category_id=gpu_category["id"],
        price=67990.00,
        quantity=5,
        description="Видеокарта среднего-высокого класса",
        specifications=[
            {"name": "CUDA-ядер", "value": "5888"},
            {"name": "Шина памяти", "value": "192-bit"},
        ],
    )

    rx_7800_xt = get_or_create_product(
        name="AMD Radeon RX 7800 XT",
        category_id=gpu_category["id"],
        price=59990.00,
        quantity=6,
        description="Видеокарта на архитектуре RDNA 3",
        specifications=[
            {"name": "Потоковых процессоров", "value": "3840"},
            {"name": "Шина памяти", "value": "256-bit"},
        ],
    )

    # 8. Product parameter values
    set_product_parameter(
        ryzen_7600x["id"],
        p_cpu_vendor["id"],
        enum_value_id=amd["id"],
    )
    set_product_parameter(
        ryzen_7600x["id"],
        p_socket["id"],
        enum_value_id=am5["id"],
    )
    set_product_parameter(
        ryzen_7600x["id"],
        p_base_frequency["id"],
        val_real=4.7,
    )
    set_product_parameter(
        ryzen_7600x["id"],
        p_tdp["id"],
        val_int=105,
    )
    set_product_parameter(
        ryzen_7600x["id"],
        p_tech_process["id"],
        val_int=5,
    )

    set_product_parameter(
        intel_13600k["id"],
        p_cpu_vendor["id"],
        enum_value_id=intel["id"],
    )
    set_product_parameter(
        intel_13600k["id"],
        p_socket["id"],
        enum_value_id=lga1700["id"],
    )
    set_product_parameter(
        intel_13600k["id"],
        p_base_frequency["id"],
        val_real=3.5,
    )
    set_product_parameter(
        intel_13600k["id"],
        p_tdp["id"],
        val_int=125,
    )
    set_product_parameter(
        intel_13600k["id"],
        p_tech_process["id"],
        val_int=10,
    )

    set_product_parameter(
        rtx_4070["id"],
        p_gpu_memory_type["id"],
        enum_value_id=gddr6x["id"],
    )
    set_product_parameter(
        rtx_4070["id"],
        p_gpu_memory_size["id"],
        val_int=12,
    )
    set_product_parameter(
        rtx_4070["id"],
        p_tdp["id"],
        val_int=200,
    )

    set_product_parameter(
        rx_7800_xt["id"],
        p_gpu_memory_type["id"],
        enum_value_id=gddr6["id"],
    )
    set_product_parameter(
        rx_7800_xt["id"],
        p_gpu_memory_size["id"],
        val_int=16,
    )
    set_product_parameter(
        rx_7800_xt["id"],
        p_tdp["id"],
        val_int=263,
    )

    print("[DONE] seed completed")

    print("\nПроверка:")
    print(f"{BASE_URL}/tree")
    print(f"{BASE_URL}/categories/{cpu_category['id']}/products-with-parameters")
    print(f"{BASE_URL}/categories/{gpu_category['id']}/products-with-parameters")


if __name__ == "__main__":
    main()
