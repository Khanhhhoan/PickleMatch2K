from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import deps
from app.models.user import User, UserRole
from app.schemas.ml import PredictMatchRequest, PredictMatchResponse, SurveyAnswersRequest
from app.services import ml_service

router = APIRouter()


@router.get("/model-info")
def model_info(db: Session = Depends(deps.get_db), current_user: User = Depends(deps.get_current_active_user)):
    """
    Trạng thái mô hình ghép cặp (Random Forest): đặc trưng, nguồn dữ liệu huấn luyện (phiếu mô phỏng, khảo sát thật
    hay dữ liệu tổng hợp khởi tạo), cách đánh giá, các chỉ số và ngưỡng đề xuất phòng đấu.
    Người chơi nhận thêm danh sách mục hồ sơ còn thiếu để mô hình chấm điểm chính xác.
    """
    info = ml_service.match_predictor.info()
    if current_user.role == UserRole.ADMIN.value:
        info["survey"] = ml_service.feedback_summary(db)
    elif current_user.role == UserRole.PLAYER.value:
        info["missing_profile_fields"] = ml_service.missing_profile_fields(current_user)
    return info


@router.post("/predict-match", response_model=PredictMatchResponse)
def predict_match(
    request: PredictMatchRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Xác suất phù hợp giữa người đang đăng nhập và một người chơi khác."""
    user_a = current_user
    if current_user.role == UserRole.ADMIN.value and request.user_a_id:
        user_a = db.query(User).filter(User.id == request.user_a_id).first()
    user_b = db.query(User).filter(User.id == request.user_b_id).first()
    if not user_a or not user_b:
        raise HTTPException(status_code=404, detail="Không tìm thấy người chơi")
    return ml_service.predict_pair(user_a, user_b)


@router.get("/recommend-partners")
def recommend_partners(
    limit: int = Query(8, ge=1, le=50),
    latitude: Optional[float] = Query(None, ge=-90, le=90),
    longitude: Optional[float] = Query(None, ge=-180, le=180),
    radius_km: Optional[float] = Query(None, gt=0, le=200),
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    """
    Top-N người chơi phù hợp nhất theo mô hình Random Forest. Trả về thông tin mô hình, các trường
    hồ sơ còn thiếu của người gọi, và danh sách ứng viên (không kèm email hay số điện thoại).
    """
    return ml_service.recommend_partners(db, current_user, latitude, longitude, radius_km, limit)


@router.get("/survey/pairs")
def survey_pairs(
    count: int = Query(10, ge=1, le=30),
    current_user: User = Depends(deps.get_current_active_user),
):
    """Các cặp hồ sơ giả định để người chơi trả lời "có muốn ghép không" (thu nhãn thật cho mô hình)."""
    pairs, missing = ml_service.generate_survey_pairs(current_user, count)
    return {"pairs": pairs, "missing_profile_fields": missing}


@router.post("/survey/answers")
def survey_answers(
    payload: SurveyAnswersRequest,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_active_user),
):
    saved = ml_service.save_survey_answers(db, current_user, payload.answers)
    return {"saved": saved}
