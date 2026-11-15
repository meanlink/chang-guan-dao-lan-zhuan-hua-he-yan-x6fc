from pydantic import BaseModel, Field
class QuotaAllocateInput(BaseModel):
    user_id: int
    total: int = Field(ge=0)
