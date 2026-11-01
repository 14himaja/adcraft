from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


PostType = Literal[
    "product_promotion",
    "special_offer",
    "discount",
    "announcement",
    "event",
    "educational",
    "general_business",
    "other",
]

OfferStatus = Literal[
    "ACTIVE",
    "EXPIRED",
    "INACTIVE",
    "UNKNOWN_VALIDITY",
    "PENDING_VERIFICATION",
]

KnowledgeStatus = Literal[
    "PENDING",
    "PROCESSING",
    "READY",
    "FAILED",
    "OUTDATED",
    "DELETED",
]

PostStatus = Literal[
    "published",
    "deleted",
    "archived",
]

AdCampaignStatus = Literal[
    "none",
    "active",
    "paused",
    "stopped",
    "completed",
]


class ExtractedProduct(BaseModel):
    name: str = Field(description="Name of the product or service")
    price: float | None = Field(default=None, description="Exact price if stated, else null")
    currency: str = Field(default="INR", description="Currency ISO code")
    description: str = Field(default="", description="Short description of the product")


class ExtractedOffer(BaseModel):
    description: str = Field(description="Description of the offer, discount or bundle")
    price: float | None = Field(default=None, description="Offer price if explicitly stated, else null")
    currency: str = Field(default="INR", description="Currency ISO code")
    discount: str | None = Field(default=None, description="Discount amount or percentage, e.g. '20% off'")
    valid_from: str | None = Field(default=None, description="Start date in YYYY-MM-DD format if stated, else null")
    valid_until: str | None = Field(default=None, description="Expiry date in YYYY-MM-DD format if stated, else null")
    terms_and_conditions: list[str] = Field(default_factory=list, description="Conditions, limits or restrictions")
    status: OfferStatus = Field(default="UNKNOWN_VALIDITY", description="Offer status")


class ExtractedFaq(BaseModel):
    question: str = Field(description="Anticipated customer question")
    answer: str = Field(description="Factual answer strictly derived from the post")


class PostUnderstandingOutput(BaseModel):
    post_type: PostType = Field(description="Classified category of the post")
    subject: str = Field(description="Main subject and core purpose of the post")
    summary: str = Field(description="Concise, factual 1-3 sentence summary of the post")
    products: list[ExtractedProduct] = Field(default_factory=list, description="Products and services mentioned")
    offer: ExtractedOffer | None = Field(default=None, description="Offer details if any promotion or discount is present")
    target_audience: str | None = Field(default=None, description="Target customer group if clearly identifiable")
    contact_or_purchase_instructions: str | None = Field(default=None, description="How customers can buy, book or contact")
    anticipated_faqs: list[ExtractedFaq] = Field(default_factory=list, description="Frequently anticipated questions and factual answers")
    keywords: list[str] = Field(default_factory=list, description="Semantic keywords for indexing and search")
    confidence_score: float = Field(default=1.0, description="Extraction confidence score between 0.0 and 1.0")

