"""Data models for the Invoice Ninja SDK.

Every model is a dataclass whose field names follow the Go SDK naming
convention and serialize to the snake_case JSON keys used by the Invoice Ninja
API. Serialization mirrors Go's ``omitempty`` semantics: zero values (empty
strings, 0, 0.0, False, None and empty lists) are omitted from request bodies,
except for fields listed in ``_always_serialize`` whose Go tags have no
``omitempty``. Unknown fields in responses are ignored, like Go's json
package.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Any, ClassVar, Dict, Generic, List, Optional, Type, TypeVar

__all__ = [
    "Model",
    "Payment",
    "PaymentRequest",
    "PaymentInvoice",
    "PaymentCredit",
    "Paymentable",
    "Invoice",
    "LineItem",
    "INClient",
    "ClientContact",
    "Credit",
    "PaymentTerm",
    "Meta",
    "Pagination",
    "Links",
    "ListResponse",
    "BulkAction",
    "RefundRequest",
    "StatementRequest",
    "ClientPortalSwitchRequest",
    "ClientPortalSwitchResponse",
    "parse_list_response",
    "parse_single_response",
]

T = TypeVar("T")


def _snake_case(name: str) -> str:
    """Convert a Go-style field name to its snake_case JSON key."""
    out: List[str] = []
    for i, char in enumerate(name):
        if char.isupper():
            if i > 0:
                prev = name[i - 1]
                next_lower = i + 1 < len(name) and not (name[i + 1].isupper() or name[i + 1].isdigit())
                if (not prev.isupper() and not prev.isdigit()) or next_lower:
                    out.append("_")
            out.append(char.lower())
        else:
            out.append(char)
    return "".join(out)


def _is_empty(value: Any) -> bool:
    """Report whether *value* is a Go-style zero value for omitempty."""
    if value is None:
        return True
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value == 0
    if isinstance(value, str):
        return value == ""
    if isinstance(value, (list, tuple)):
        return len(value) == 0
    return False


def _coerce(name: str, raw: Any, annotation: str) -> Any:
    if annotation == "float":
        if isinstance(raw, bool):
            raise ValueError("expected a number, got a bool")
        return float(raw)
    if annotation == "int":
        if isinstance(raw, bool):
            return int(raw)
        if isinstance(raw, float) and not raw.is_integer():
            raise ValueError("expected an integer")
        return int(raw)
    if annotation == "bool":
        return bool(raw)
    return raw


class Model:
    """Base class for JSON-serializable Invoice Ninja models."""

    #: Field names whose JSON keys differ from the snake_case derivation.
    _json_overrides: ClassVar[Dict[str, str]] = {}
    #: Field name -> nested Model class, or a 1-tuple of a Model class for lists.
    _nested: ClassVar[Dict[str, Any]] = {}
    #: Field names never omitted from serialization (no omitempty in Go tags).
    _always_serialize: ClassVar[frozenset] = frozenset()

    @classmethod
    def _key_for(cls, field_name: str) -> str:
        return cls._json_overrides.get(field_name, _snake_case(field_name))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dict, omitting zero values like Go's ``omitempty``."""
        result: Dict[str, Any] = {}
        for f in fields(self):  # type: ignore[arg-type]
            value = getattr(self, f.name)
            if f.name not in self._always_serialize and _is_empty(value):
                continue
            key = self._key_for(f.name)
            if isinstance(value, Model):
                value = value.to_dict()
            elif isinstance(value, (list, tuple)):
                value = [item.to_dict() if isinstance(item, Model) else item for item in value]
            result[key] = value
        return result

    def to_json(self) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls: Type[T], data: Optional[Dict[str, Any]]) -> T:
        """Build a model from an API response dict, ignoring unknown fields."""
        if data is None:
            return cls()  # type: ignore[return-value]
        if not isinstance(data, dict):
            raise ValueError(f"expected a dict to build {cls.__name__}, got {type(data).__name__}")
        kwargs: Dict[str, Any] = {}
        for f in fields(cls):
            key = cls._key_for(f.name)
            if key not in data or data[key] is None:
                continue
            raw = data[key]
            nested = cls._nested.get(f.name)
            try:
                if nested is not None:
                    if isinstance(nested, tuple):
                        if not isinstance(raw, list):
                            raise ValueError("expected a list")
                        kwargs[f.name] = [nested[0].from_dict(item) for item in raw]
                    else:
                        kwargs[f.name] = nested.from_dict(raw)
                else:
                    kwargs[f.name] = _coerce(f.name, raw, f.type)
            except (TypeError, ValueError) as err:
                raise ValueError(f"invalid value for field {f.name!r}: {err}") from err
        return cls(**kwargs)


@dataclass
class Paymentable(Model):
    """A paymentable entity (invoice or credit attached to a payment)."""

    id: str = ""
    invoice_id: str = ""
    credit_id: str = ""
    refunded: float = 0.0
    amount: float = 0.0
    updated_at: int = 0
    created_at: int = 0


@dataclass
class PaymentInvoice(Model):
    """An invoice applied to a payment."""

    invoice_id: str = ""
    amount: float = 0.0


@dataclass
class PaymentCredit(Model):
    """A credit applied to a payment."""

    credit_id: str = ""
    amount: float = 0.0


@dataclass
class Payment(Model):
    """A payment in Invoice Ninja."""

    id: str = ""
    client_id: str = ""
    invitation_id: str = ""
    client_contact_id: str = ""
    user_id: str = ""
    type_id: str = ""
    date: str = ""
    transaction_ref: str = ""
    assigned_user_id: str = ""
    private_notes: str = ""
    is_manual: bool = False
    is_deleted: bool = False
    amount: float = 0.0
    refunded: float = 0.0
    updated_at: int = 0
    archived_at: int = 0
    company_gateway_id: str = ""
    number: str = ""
    category_id: str = ""
    custom_value1: str = ""
    custom_value2: str = ""
    custom_value3: str = ""
    custom_value4: str = ""
    exchange_currency_id: str = ""
    exchange_rate: float = 0.0
    idempotency_key: str = ""
    paymentables: List[Paymentable] = field(default_factory=list)
    invoices: List[PaymentInvoice] = field(default_factory=list)
    credits: List[PaymentCredit] = field(default_factory=list)

    _json_overrides: ClassVar[Dict[str, str]] = {"transaction_ref": "transaction_reference"}
    _nested: ClassVar[Dict[str, Any]] = {
        "paymentables": (Paymentable,),
        "invoices": (PaymentInvoice,),
        "credits": (PaymentCredit,),
    }


@dataclass
class PaymentRequest(Model):
    """A request to create or update a payment."""

    client_id: str = ""
    client_contact_id: str = ""
    user_id: str = ""
    type_id: str = ""
    date: str = ""
    transaction_ref: str = ""
    assigned_user_id: str = ""
    private_notes: str = ""
    amount: float = 0.0
    invoices: List[PaymentInvoice] = field(default_factory=list)
    credits: List[PaymentCredit] = field(default_factory=list)
    number: str = ""

    _json_overrides: ClassVar[Dict[str, str]] = {"transaction_ref": "transaction_reference"}
    _nested: ClassVar[Dict[str, Any]] = {
        "invoices": (PaymentInvoice,),
        "credits": (PaymentCredit,),
    }


@dataclass
class LineItem(Model):
    """A line item on an invoice, credit or quote."""

    quantity: float = 0.0
    cost: float = 0.0
    product_key: str = ""
    notes: str = ""
    discount: float = 0.0
    is_amount_discount: bool = False
    tax_name1: str = ""
    tax_rate1: float = 0.0
    tax_name2: str = ""
    tax_rate2: float = 0.0
    tax_name3: str = ""
    tax_rate3: float = 0.0
    custom_value1: str = ""
    custom_value2: str = ""
    custom_value3: str = ""
    custom_value4: str = ""
    type_id: str = ""


@dataclass
class Invoice(Model):
    """An invoice in Invoice Ninja."""

    id: str = ""
    user_id: str = ""
    assigned_user_id: str = ""
    client_id: str = ""
    status_id: str = ""
    number: str = ""
    po_number: str = ""
    terms: str = ""
    public_notes: str = ""
    private_notes: str = ""
    footer: str = ""
    custom_value1: str = ""
    custom_value2: str = ""
    custom_value3: str = ""
    custom_value4: str = ""
    tax_name1: str = ""
    tax_name2: str = ""
    tax_name3: str = ""
    tax_rate1: float = 0.0
    tax_rate2: float = 0.0
    tax_rate3: float = 0.0
    total_taxes: float = 0.0
    amount: float = 0.0
    balance: float = 0.0
    paid_to_date: float = 0.0
    discount: float = 0.0
    partial_due_date: str = ""
    due_date: str = ""
    date: str = ""
    line_items: List[LineItem] = field(default_factory=list)
    is_deleted: bool = False
    uses_inclusive_taxes: bool = False
    updated_at: int = 0
    archived_at: int = 0
    created_at: int = 0

    _nested: ClassVar[Dict[str, Any]] = {"line_items": (LineItem,)}


@dataclass
class ClientContact(Model):
    """A contact for a client."""

    id: str = ""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    is_primary: bool = False
    contact_key: str = ""
    custom_value1: str = ""
    custom_value2: str = ""
    custom_value3: str = ""
    custom_value4: str = ""


@dataclass
class INClient(Model):
    """A client in Invoice Ninja.

    Named ``INClient`` (like the Go SDK) to avoid clashing with the API
    :class:`~invoice_ninja.client.Client`.
    """

    id: str = ""
    user_id: str = ""
    assigned_user_id: str = ""
    name: str = ""
    website: str = ""
    private_notes: str = ""
    public_notes: str = ""
    balance: float = 0.0
    paid_to_date: float = 0.0
    credit_balance: float = 0.0
    phone: str = ""
    address1: str = ""
    address2: str = ""
    city: str = ""
    state: str = ""
    postal_code: str = ""
    country_id: str = ""
    industry_id: str = ""
    custom_value1: str = ""
    custom_value2: str = ""
    custom_value3: str = ""
    custom_value4: str = ""
    vat_number: str = ""
    id_number: str = ""
    number: str = ""
    shipping_address1: str = ""
    shipping_address2: str = ""
    shipping_city: str = ""
    shipping_state: str = ""
    shipping_postal: str = ""
    shipping_country: str = ""
    is_deleted: bool = False
    contacts: List[ClientContact] = field(default_factory=list)
    updated_at: int = 0
    archived_at: int = 0
    created_at: int = 0

    _json_overrides: ClassVar[Dict[str, str]] = {
        "shipping_postal": "shipping_postal_code",
        "shipping_country": "shipping_country_id",
    }
    _nested: ClassVar[Dict[str, Any]] = {"contacts": (ClientContact,)}


@dataclass
class Credit(Model):
    """A credit note in Invoice Ninja."""

    id: str = ""
    user_id: str = ""
    assigned_user_id: str = ""
    client_id: str = ""
    status_id: str = ""
    invoice_id: str = ""
    number: str = ""
    po_number: str = ""
    terms: str = ""
    public_notes: str = ""
    private_notes: str = ""
    footer: str = ""
    custom_value1: str = ""
    custom_value2: str = ""
    custom_value3: str = ""
    custom_value4: str = ""
    tax_name1: str = ""
    tax_name2: str = ""
    tax_name3: str = ""
    tax_rate1: float = 0.0
    tax_rate2: float = 0.0
    tax_rate3: float = 0.0
    total_taxes: float = 0.0
    amount: float = 0.0
    balance: float = 0.0
    paid_to_date: float = 0.0
    discount: float = 0.0
    partial: float = 0.0
    is_amount_discount: bool = False
    is_deleted: bool = False
    uses_inclusive_taxes: bool = False
    date: str = ""
    last_sent_date: str = ""
    next_send_date: str = ""
    partial_due_date: str = ""
    due_date: str = ""
    line_items: List[LineItem] = field(default_factory=list)
    updated_at: int = 0
    archived_at: int = 0
    created_at: int = 0

    _nested: ClassVar[Dict[str, Any]] = {"line_items": (LineItem,)}


@dataclass
class PaymentTerm(Model):
    """A payment term in Invoice Ninja."""

    id: str = ""
    name: str = ""
    num_days: int = 0
    is_default: bool = False
    is_deleted: bool = False
    created_at: int = 0
    updated_at: int = 0
    archived_at: int = 0


@dataclass
class Links(Model):
    """Pagination links."""

    next: str = ""
    previous: str = ""


@dataclass
class Pagination(Model):
    """Pagination details."""

    total: int = 0
    count: int = 0
    per_page: int = 0
    current_page: int = 0
    total_pages: int = 0
    links: Optional[Links] = None

    _nested: ClassVar[Dict[str, Any]] = {"links": Links}


@dataclass
class Meta(Model):
    """Pagination metadata."""

    pagination: Optional[Pagination] = None

    _nested: ClassVar[Dict[str, Any]] = {"pagination": Pagination}


@dataclass
class ListResponse(Model, Generic[T]):  # type: ignore[type-arg,misc]
    """A generic response structure for list endpoints."""

    data: List[Any] = field(default_factory=list)
    meta: Optional[Meta] = None

    _nested: ClassVar[Dict[str, Any]] = {"meta": Meta}

    def __iter__(self):
        return iter(self.data)

    def __len__(self) -> int:
        return len(self.data)

    def __getitem__(self, index):
        return self.data[index]


@dataclass
class BulkAction(Model):
    """A bulk action request."""

    action: str = ""
    ids: List[str] = field(default_factory=list)

    _always_serialize: ClassVar[frozenset] = frozenset({"action", "ids"})


@dataclass
class RefundRequest(Model):
    """A refund request."""

    id: str = ""
    amount: float = 0.0
    invoices: List[PaymentInvoice] = field(default_factory=list)
    date: str = ""
    gateway_refund: bool = False
    send_email: bool = False

    _always_serialize: ClassVar[frozenset] = frozenset({"id"})
    _nested: ClassVar[Dict[str, Any]] = {"invoices": (PaymentInvoice,)}


@dataclass
class StatementRequest(Model):
    """A client statement request."""

    client_id: str = ""
    start_date: str = ""
    end_date: str = ""
    show_payments_table: bool = False
    show_aging_table: bool = False
    show_credits_table: bool = False
    status: str = ""

    _always_serialize: ClassVar[frozenset] = frozenset({"client_id"})


@dataclass
class ClientPortalSwitchRequest(Model):
    """A request to switch to the client portal."""

    contact_id: str = ""


@dataclass
class ClientPortalSwitchResponse(Model):
    """The response from switching to the client portal."""

    url: str = ""

    _always_serialize: ClassVar[frozenset] = frozenset({"url"})


def parse_single_response(payload: Dict[str, Any], item_cls: Type[T]) -> T:
    """Parse a ``{"data": {...}}`` single-entity response."""
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object response")
    data = payload.get("data")
    if data is None:
        return item_cls()
    return item_cls.from_dict(data)


def parse_list_response(payload: Dict[str, Any], item_cls: Type[T]) -> ListResponse[T]:
    """Parse a ``{"data": [...], "meta": {...}}`` list response."""
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object response")
    raw_data = payload.get("data")
    if raw_data is None:
        raw_data = []
    if not isinstance(raw_data, list):
        raise ValueError("expected 'data' to be a list")
    items = [item_cls.from_dict(item) if item is not None else item_cls() for item in raw_data]
    meta = Meta.from_dict(payload.get("meta"))
    return ListResponse(items, meta)
