from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.sql import func

from app.db.base_class import Base


SURVEY_SOURCE = "survey"        # câu trả lời khảo sát của người chơi thật
SIMULATED_SOURCE = "simulated"  # phiếu mô phỏng nạp sẵn để minh họa quy trình (python manage.py seed --feedback)


class PairFeedback(Base):
    """
    Nhãn cho mô hình ghép cặp: một người chơi trả lời "có muốn ghép với người này không" cho một cặp hồ sơ.
    Mỗi dòng lưu đúng 4 đặc trưng mà mô hình dùng. Cột `source` phân biệt câu trả lời khảo sát thật (survey)
    với phiếu mô phỏng nạp sẵn (simulated); hai loại không bao giờ được trình bày lẫn với nhau.
    """
    __tablename__ = "pair_feedback"

    id = Column(Integer, primary_key=True, index=True)
    rater_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    source = Column(String, nullable=False, default="survey", server_default="survey")
    level_diff = Column(Float, nullable=False)
    distance_km = Column(Float, nullable=False)
    purpose_match = Column(Integer, nullable=False)
    style_match = Column(Integer, nullable=False)
    label = Column(Integer, nullable=False)  # 1 = muốn ghép, 0 = không
    created_at = Column(DateTime(timezone=True), server_default=func.now())
