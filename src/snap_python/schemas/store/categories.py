# generated by datamodel-codegen:
#   filename:  category_schema.json
#   timestamp: 2024-09-17T00:34:03+00:00

from typing import List, Optional

from pydantic import BaseModel, ConfigDict

VALID_CATEGORY_FIELDS = ["name", "type", "title", "summary", "description", "media"]


class Media(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    height: Optional[float] = None
    type: str
    url: str
    width: Optional[float] = None


class Category(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    description: Optional[str] = None
    media: Optional[Media] = None
    name: Optional[str] = None
    summary: Optional[str] = None
    title: Optional[str] = None
    type: Optional[str] = None
    featured: Optional[bool] = None


class CategoryResponse(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    categories: Optional[List[Category]] = None


class SingleCategoryResponse(BaseModel):
    model_config = ConfigDict(exclude_unset=True)

    category: Category
