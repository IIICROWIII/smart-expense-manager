"""Strict API input contracts. Monetary amounts are decimal strings."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

Kind = Literal["expense", "income"]
Method = Literal["Card", "Cash", "Istanbulkart", "Bank Transfer", "Other"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class TransactionInput(InputModel):
    amount: str = Field(max_length=32, examples=["125.50"])
    kind: Kind
    category_id: int = Field(gt=0)
    date: str = Field(max_length=10, examples=["2026-10-13"])
    description: str = Field(default="", max_length=500)
    payment_method: Method = "Card"


class TransactionPatch(InputModel):
    amount: str = Field(default=None, max_length=32)
    kind: Kind = None
    category_id: int = Field(default=None, gt=0)
    date: str = Field(default=None, max_length=10)
    description: str = Field(default=None, max_length=500)
    payment_method: Method = None


class BudgetInput(InputModel):
    month: str = Field(max_length=7)
    amount: str = Field(max_length=32)
    category_id: int | None = Field(default=None, gt=0)


class CopyBudgetInput(InputModel):
    month: str = Field(max_length=7)


class SuggestionInput(InputModel):
    description: str = Field(max_length=500)
    kind: Kind = "expense"
