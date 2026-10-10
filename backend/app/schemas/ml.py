from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PredictMatchRequest(BaseModel):
    user_b_id: int
    # Giữ để tương thích; luôn bị thay bằng người đang đăng nhập (trừ Admin)
    user_a_id: Optional[int] = None


class PredictMatchResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_available: bool
    is_match_recommended: Optional[bool] = None
    success_probability: Optional[float] = None
    features_used: dict


class SurveyAnswer(BaseModel):
    features: Dict[str, float]
    signature: str
    label: bool


class SurveyAnswersRequest(BaseModel):
    answers: List[SurveyAnswer] = Field(min_length=1, max_length=50)
