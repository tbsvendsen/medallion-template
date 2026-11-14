"""Generate synthetic order data for the pipeline."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from faker import Faker

from medallion.models import (
    Customer,
    CustomerSegment,
    Delivery,
    DeliveryStatus,
    Order,
    OrderLine,
    OrderStatus,
    Product,
)

SEED = 42
CATEGORIES = {
    "Electronics": ["Laptops", "Phones", "Tablets", "Accessories"],
    "Clothing": ["Shirts", "Pants", "Shoes", "Jackets"],
    "Home": ["Furniture", "Kitchen", "Lighting", "Decor"],
    "Sports": ["Equipment", "Apparel", "Footwear", "Accessories"],
}


def create_generator(seed: int = SEED) -> Faker:
    fake = Faker(["en_US"])
    Faker.seed(seed)
    return fake


def generate_customers(fake: Faker, count: int = 200) -> list[Customer]:
    segments = list(CustomerSegment)
    weights = [0.6, 0.3, 0.1]  # retail heavy
    customers: list[Customer] = []
    for i in range(count):
        segment = fake.random_element(
            elements=OrderedDict(zip(segments, weights, strict=False))
        )
        customers.append(
            Customer(
                customer_id=f"C-{i + 1:05d}",
                name=fake.name(),
                email=fake.email(),
                address=fake.street_address(),
                city=fake.city(),
                country=fake.random_element(
                    elements=["Norway", "Sweden", "Denmark", "Finland"]
                ),
                segment=segment,
                created_at=fake.date_time_between(start_date="-3y", end_date="-6M"),
            )
        )
    return customers


def generate_products(fake: Faker, count: int = 50) -> list[Product]:
    products: list[Product] = []
    i = 0
    for category, subcategories in CATEGORIES.items():
        per_sub = max(1, count // (len(CATEGORIES) * len(subcategories)))
        for subcategory in subcategories:
            for _ in range(per_sub):
                if i >= count:
                    return products
                products.append(
                    Product(
                        product_id=f"P-{i + 1:04d}",
                        name=fake.catch_phrase(),
                        category=category,
                        subcategory=subcategory,
                        unit_price=round(fake.pyfloat(min_value=5, max_value=2000), 2),
                        weight_kg=round(fake.pyfloat(min_value=0.1, max_value=30), 2),
                    )
                )
                i += 1
    return products


def generate_orders(
    fake: Faker,
    customers: list[Customer],
    products: list[Product],
    count: int = 1000,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[Order]:
    if start_date is None:
        start_date = date.today() - timedelta(days=365)
    if end_date is None:
        end_date = date.today()

    statuses = list(OrderStatus)
    status_weights = [0.05, 0.15, 0.30, 0.45, 0.05]
    orders: list[Order] = []

    for i in range(count):
        customer = fake.random_element(elements=customers)
        order_date = fake.date_between(start_date=start_date, end_date=end_date)
        num_lines = fake.random_int(min=1, max=min(5, len(products)))
        chosen_products = fake.random_elements(
            elements=products, length=num_lines, unique=True
        )
        lines = [
            OrderLine(
                order_id=f"O-{i + 1:06d}",
                line_number=j + 1,
                product_id=p.product_id,
                quantity=fake.random_int(min=1, max=10),
                unit_price=p.unit_price,
                discount_pct=fake.random_element(elements=[0, 0, 0, 5, 10, 15]),
            )
            for j, p in enumerate(chosen_products)
        ]
        orders.append(
            Order(
                order_id=f"O-{i + 1:06d}",
                customer_id=customer.customer_id,
                order_date=order_date,
                status=fake.random_element(
                    elements=OrderedDict(zip(statuses, status_weights, strict=False))
                ),
                lines=lines,
            )
        )
    return orders


def generate_deliveries(fake: Faker, orders: list[Order]) -> list[Delivery]:
    deliveries: list[Delivery] = []
    for order in orders:
        if order.status in (OrderStatus.PENDING, OrderStatus.CANCELLED):
            continue
        shipped = order.order_date + timedelta(days=fake.random_int(min=1, max=5))
        delivered = (
            shipped + timedelta(days=fake.random_int(min=1, max=10))
            if order.status in (OrderStatus.DELIVERED,)
            else None
        )
        status = {
            OrderStatus.CONFIRMED: DeliveryStatus.PROCESSING,
            OrderStatus.SHIPPED: DeliveryStatus.IN_TRANSIT,
            OrderStatus.DELIVERED: DeliveryStatus.DELIVERED,
        }[order.status]

        deliveries.append(
            Delivery(
                delivery_id=f"D-{len(deliveries) + 1:06d}",
                order_id=order.order_id,
                status=status,
                shipped_date=shipped,
                delivered_date=delivered,
                tracking_id=(
                    fake.uuid4()[:12] if status != DeliveryStatus.PROCESSING else None
                ),
            )
        )
    return deliveries


def _to_dicts(items: list[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in items]


def generate_raw_api_responses(
    output_dir: Path,
    num_customers: int = 200,
    num_products: int = 50,
    num_orders: int = 1000,
) -> dict[str, Path]:
    """Simulate API responses as raw JSON files.

    Returns a mapping of entity name to output file path.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    fake = create_generator()
    customers = generate_customers(fake, num_customers)
    products = generate_products(fake, num_products)
    orders = generate_orders(fake, customers, products, num_orders)
    deliveries = generate_deliveries(fake, orders)

    # Flatten order lines into their own entity
    order_headers = [
        {
            "order_id": o.order_id,
            "customer_id": o.customer_id,
            "order_date": o.order_date.isoformat(),
            "status": o.status.value,
        }
        for o in orders
    ]
    order_lines = [line.model_dump(mode="json") for o in orders for line in o.lines]

    datasets: dict[str, list[dict[str, Any]]] = {
        "customers": _to_dicts(customers),
        "products": _to_dicts(products),
        "orders": order_headers,
        "order_lines": order_lines,
        "deliveries": _to_dicts(deliveries),
    }

    paths: dict[str, Path] = {}
    for name, records in datasets.items():
        path = output_dir / f"{name}.json"
        path.write_text(json.dumps(records, indent=2, default=str))
        paths[name] = path

    return paths
