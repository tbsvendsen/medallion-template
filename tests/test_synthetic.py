"""Tests for synthetic data generation."""

from __future__ import annotations

import json
from pathlib import Path

from medallion.synthetic import (
    create_generator,
    generate_customers,
    generate_deliveries,
    generate_orders,
    generate_products,
    generate_raw_api_responses,
)


class TestSyntheticGeneration:
    def test_deterministic_with_same_seed(self) -> None:
        fake1 = create_generator(seed=42)
        customers1 = generate_customers(fake1, count=5)
        fake2 = create_generator(seed=42)
        customers2 = generate_customers(fake2, count=5)
        ids1 = [c.customer_id for c in customers1]
        ids2 = [c.customer_id for c in customers2]
        assert ids1 == ids2
        assert [c.name for c in customers1] == [c.name for c in customers2]

    def test_customers_have_valid_segments(self) -> None:
        fake = create_generator()
        customers = generate_customers(fake, count=50)
        segments = {c.segment.value for c in customers}
        assert segments <= {"retail", "wholesale", "enterprise"}

    def test_products_have_positive_prices(self) -> None:
        fake = create_generator()
        products = generate_products(fake, count=20)
        assert all(p.unit_price > 0 for p in products)

    def test_orders_reference_valid_customers(self) -> None:
        fake = create_generator()
        customers = generate_customers(fake, count=10)
        products = generate_products(fake, count=5)
        orders = generate_orders(fake, customers, products, count=20)
        customer_ids = {c.customer_id for c in customers}
        assert all(o.customer_id in customer_ids for o in orders)

    def test_order_lines_have_valid_quantities(self) -> None:
        fake = create_generator()
        customers = generate_customers(fake, count=10)
        products = generate_products(fake, count=5)
        orders = generate_orders(fake, customers, products, count=20)
        for order in orders:
            for line in order.lines:
                assert line.quantity >= 1
                assert line.unit_price > 0

    def test_deliveries_skip_pending_and_cancelled(self) -> None:
        fake = create_generator()
        customers = generate_customers(fake, count=20)
        products = generate_products(fake, count=10)
        orders = generate_orders(fake, customers, products, count=100)
        deliveries = generate_deliveries(fake, orders)
        delivery_order_ids = {d.order_id for d in deliveries}
        for order in orders:
            if order.status.value in ("pending", "cancelled"):
                assert order.order_id not in delivery_order_ids

    def test_raw_api_responses_creates_all_files(self, tmp_path: Path) -> None:
        paths = generate_raw_api_responses(
            tmp_path, num_customers=5, num_products=3, num_orders=10
        )
        expected = {"customers", "products", "orders", "order_lines", "deliveries"}
        assert set(paths.keys()) == expected
        for name, path in paths.items():
            assert path.exists()
            records = json.loads(path.read_text())
            assert len(records) > 0, f"{name} should have records"
