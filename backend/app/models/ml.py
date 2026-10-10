from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.db.base_class import Base


class PairFeedback(Base):
    """
    Nhãn thật cho mô hình ghép cặp: một người chơi trả lời "có muốn ghép với người này không"
    cho một cặp hồ sơ (khảo sát trong ứng dụng). Mỗi dòng lưu đúng 5 đặc trưng mà mô hình dùng.
    """
    __tablename__ = "pair_feedback"

    id = Column(Integer, primary_key=True, index=True)
    rater_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, nullable=False, default="survey", server_default="survey")
    level_diff = Column(Float, nullable=False)
    distance_km = Column(Float, nullable=False)
    availability_overlap = Column(Float, nullable=False)
    purpose_match = Column(Integer, nullable=False)
    style_match = Column(Integer, nullable=False)
    label = Column(Integer, nullable=False)  # 1 = muốn ghép, 0 = không
    created_at = Column(DateTime(timezone=True), server_default=func.now())
