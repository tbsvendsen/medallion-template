"""Domain models for the order data pipeline."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class CustomerSegment(StrEnum):
    RETAIL = "retail"
    WHOLESALE = "wholesale"
    ENTERPRISE = "enterprise"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class DeliveryStatus(StrEnum):
    PROCESSING = "processing"
    IN_TRANSIT = "in_transit"
    DELIVERED = "delivered"
    RETURNED = "returned"


class Customer(BaseModel):
    customer_id: str
    name: str
    email: str
    address: str
    city: str
    country: str
    segment: CustomerSegment
    created_at: datetime


class Product(BaseModel):
    product_id: str
    name: str
    category: str
    subcategory: str
    unit_price: float = Field(gt=0)
    weight_kg: float = Field(ge=0)


class OrderLine(BaseModel):
    order_id: str
    line_number: int = Field(ge=1)
    product_id: str
    quantity: int = Field(ge=1)
    unit_price: float = Field(gt=0)
    discount_pct: float = Field(ge=0, le=100, default=0.0)


class Order(BaseModel):
    order_id: str
    customer_id: str
    order_date: date
    status: OrderStatus
    lines: list[OrderLine]


class Delivery(BaseModel):
    delivery_id: str
    order_id: str
    status: DeliveryStatus
    shipped_date: date | None = None
    delivered_date: date | None = None
    tracking_id: str | None = None
