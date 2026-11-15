from pydantic import BaseModel, Field
class JobInput(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    dataset_id: int
    params: dict = Field(default_factory=dict)
    # 客户端为每次提交生成的幂等键，网络重试不重复建单
    idempotency_key: str | None = Field(default=None, max_length=80)
