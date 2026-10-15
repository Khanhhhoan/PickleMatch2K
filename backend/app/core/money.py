"""
Tiền VNĐ trong hệ thống luôn là số nguyên đồng: lưu cột BIGINT, tính bằng int, không dùng số thực cho tiền.

vnd() chuyển một giá trị (int, Decimal từ hàm SUM của CSDL, số từ JSON...) về số nguyên đồng. Cách làm tròn là
"về số chẵn gần nhất" (ROUND_HALF_EVEN), đúng như hàm round() mà bản trước dùng, nên không con số nghiệp vụ nào
(ví dụ tiền cọc 50% của một tổng lẻ) bị đổi khi chuyển sang số nguyên.
"""
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Union

Number = Union[int, float, Decimal, str, None]


def vnd(value: Number) -> int:
    """Số tiền (đồng) dạng số nguyên; None là 0. Báo lỗi với giá trị không phải số hữu hạn."""
    if value is None:
        return 0
    if isinstance(value, bool):
        raise TypeError("Số tiền không được là giá trị đúng/sai")
    if isinstance(value, int):
        return value
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"Số tiền không hợp lệ: {value!r}") from exc
    if not amount.is_finite():
        raise ValueError(f"Số tiền không hợp lệ: {value!r}")
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def share(total: int, rate: Union[float, Decimal]) -> int:
    """Một phần của tổng tiền theo tỷ lệ (ví dụ tiền cọc 50%), tính đúng trên số thập phân rồi làm tròn về đồng."""
    return vnd(Decimal(total) * Decimal(str(rate)))


def split_evenly(total: int, parts: int) -> list:
    """Chia tổng tiền thành `parts` phần gần bằng nhau; phần cuối nhận phần dư, nên cộng lại luôn đúng bằng tổng."""
    each = vnd(Decimal(total) / parts)
    return [each] * (parts - 1) + [total - each * (parts - 1)]
