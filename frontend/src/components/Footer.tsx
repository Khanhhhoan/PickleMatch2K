"use client";

import React, { useState } from "react";
import Link from "next/link";
import Logo from "@/components/Logo";

export default function Footer() {
  const [activePolicyModal, setActivePolicyModal] = useState<string | null>(null);

  const POLICIES_CONTENT: Record<string, { title: string; content: React.ReactNode }> = {
    booking: {
      title: "Quy Định Đặt Sân & Giữ Chỗ",
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-zinc-600 leading-relaxed">
          <p className="font-semibold text-zinc-900">1. Quy trình giữ slot trực tuyến:</p>
          <p>
            - Khi bạn chọn một khung giờ, hệ thống giữ tạm khung đó <strong>5 phút</strong> để bạn hoàn tất việc chọn. Sau khi tạo đơn, khung giờ được giữ <strong>15 phút</strong> để thanh toán cọc; quá hạn mà chưa đủ cọc thì đơn hết hiệu lực và khung giờ được trả lại.
          </p>
          <p className="font-semibold text-zinc-900">2. Đến sân đúng giờ:</p>
          <p>
            - Quý khách vui lòng có mặt tại cụm sân trước <strong>10 phút</strong> so với giờ bắt đầu để nhận sân và chuẩn bị dụng cụ.
          </p>
          <p className="font-semibold text-zinc-900">3. Trang phục thi đấu:</p>
          <p>
            - Bắt buộc đi giày thể thao đế mềm chuyên dụng cho mặt sân Pickleball/Tennis để bảo vệ mặt sân US Open.
          </p>
        </div>
      ),
    },
    deposit: {
      title: "Chính Sách Đặt Cọc 50% & Hoàn Tiền",
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-zinc-600 leading-relaxed">
          <p className="font-semibold text-zinc-900">1. Quy định đặt cọc:</p>
          <p>
            - Người chơi thanh toán đặt cọc <strong>50% tổng tiền thuê</strong> bằng chuyển khoản VietQR, ghi đúng mã đơn trong nội dung chuyển khoản. Phần còn lại thanh toán tại sân khi đến nhận sân.
          </p>
          <p className="font-semibold text-zinc-900">2. Chính sách hủy sân & hoàn cọc:</p>
          <p>
            - <strong>Hủy trước giờ chơi từ 12 tiếng trở lên</strong>: Hoàn 100% số tiền đã thanh toán.
          </p>
          <p>
            - <strong>Hủy trong vòng 6 - 12 tiếng</strong>: Không hoàn tiền cọc; bạn có thể liên hệ cụm sân để được hỗ trợ dời lịch sang khung giờ còn trống.
          </p>
          <p>
            - <strong>Hủy dưới 6 tiếng hoặc không đến</strong>: Không hoàn tiền cọc. Khoản đã trả vượt mức cọc (nếu có) vẫn được hoàn.
          </p>
          <p className="font-semibold text-zinc-900">3. Trường hợp bất khả kháng (Thời tiết xấu, sự cố kỹ thuật sân):</p>
          <p>
            - Khi cụm sân chủ động hủy lịch (mưa lớn, mất điện, bảo trì...), bạn được hoàn 100% số tiền đã thanh toán.
          </p>
        </div>
      ),
    },
    privacy: {
      title: "Chính Sách Bảo Mật & An Toàn Dữ Liệu",
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-zinc-600 leading-relaxed">
          <p className="font-semibold text-zinc-900">1. Thu thập dữ liệu:</p>
          <p>
            - PickleMatch2K chỉ thu thập các thông tin cần thiết phục vụ đặt sân (Họ tên, SĐT, Email, Trình độ DUPR) và không chia sẻ cho bất kỳ bên thứ ba nào ngoài chủ cụm sân được đặt.
          </p>
          <p className="font-semibold text-zinc-900">2. An toàn giao dịch:</p>
          <p>
            - Khoản chuyển khoản VietQR được đối soát tự động theo mã đơn; mọi khoản thu, hoàn đều được ghi vào sổ giao dịch để bạn và cụm sân cùng tra cứu.
          </p>
          <p className="font-semibold text-zinc-900">3. Quyền riêng tư của người dùng:</p>
          <p>
            - Bạn có toàn quyền cập nhật, chỉnh sửa hồ sơ hoặc yêu cầu xóa dữ liệu tài khoản bất cứ lúc nào thông qua trang Hồ Sơ Cá Nhân.
          </p>
        </div>
      ),
    },
    terms: {
      title: "Điều Khoản Sử Dụng Dịch Vụ",
      content: (
        <div className="space-y-3 text-xs sm:text-sm text-zinc-600 leading-relaxed">
          <p className="font-semibold text-zinc-900">1. Trách nhiệm người dùng:</p>
          <p>
            - Tôn trọng nội quy cụm sân, giữ gìn vệ sinh chung và bảo quản tài sản tại sân thi đấu.
          </p>
          <p className="font-semibold text-zinc-900">2. Tinh thần thể thao:</p>
          <p>
            - Khi tham gia tính năng Ghép Kèo Đấu, người chơi cam kết thi đấu trung thực, fair-play và tôn trọng bạn chơi cùng trình độ DUPR.
          </p>
          <p className="font-semibold text-zinc-900">3. Giải quyết khiếu nại:</p>
          <p>
            - Đội ngũ hỗ trợ PickleMatch2K cam kết phản hồi và xử lý mọi khiếu nại của quý khách trong vòng <strong>24 giờ làm việc</strong>.
          </p>
        </div>
      ),
    },
  };

  return (
    <>
      {/* Clean Minimalist Footer (Compact) */}
      <footer
        id="footer-policies"
        className="bg-white border-t border-zinc-200/90 text-zinc-700 font-sans mt-auto"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 sm:gap-8">
            {/* Column 1: Brand & Intro */}
            <div className="space-y-2">
              <Logo showSubtitle={false} size="sm" isLight={false} />
              <p className="text-xs text-zinc-600 leading-relaxed">
                Nền tảng đặt sân Pickleball trực tuyến và kết nối ghép trận thông minh hàng đầu tại TP. Hồ Chí Minh.
              </p>
            </div>

            {/* Column 2: Services */}
            <div>
              <h4 className="text-xs font-black text-zinc-950 uppercase tracking-wider mb-2.5">
                Dịch Vụ
              </h4>
              <ul className="space-y-1.5 text-xs text-zinc-700 font-medium">
                <li>
                  <Link href="/" className="hover:text-zinc-950 transition">
                    Tìm kiếm cụm sân gần nhất
                  </Link>
                </li>
                <li>
                  <Link href="/" className="hover:text-zinc-950 transition">
                    Đặt sân theo khung giờ
                  </Link>
                </li>
                <li>
                  <Link href="/matches" className="hover:text-zinc-950 transition">
                    Ghép trận theo điểm DUPR
                  </Link>
                </li>
                <li>
                  <Link href="/bookings" className="hover:text-zinc-950 transition">
                    Tra cứu vé & Lịch sử đặt sân
                  </Link>
                </li>
                <li>
                  <Link href="/register" className="hover:text-zinc-950 transition">
                    Đăng ký trở thành Đối tác Chủ Sân
                  </Link>
                </li>
              </ul>
            </div>

            {/* Column 3: Guide & Support */}
            <div>
              <h4 className="text-xs font-black text-zinc-950 uppercase tracking-wider mb-2.5">
                Hỗ Trợ & Quy Định
              </h4>
              <ul className="space-y-1.5 text-xs text-zinc-700 font-medium">
                <li>
                  <button
                    onClick={() => setActivePolicyModal("booking")}
                    className="hover:text-zinc-950 transition text-left cursor-pointer"
                  >
                    Hướng dẫn đặt sân & giữ chỗ
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => setActivePolicyModal("deposit")}
                    className="text-zinc-900 hover:text-zinc-950 font-bold transition text-left cursor-pointer"
                  >
                    Chính sách đặt cọc 50% & hoàn tiền
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => setActivePolicyModal("privacy")}
                    className="hover:text-zinc-950 transition text-left cursor-pointer"
                  >
                    Chính sách bảo mật thông tin
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => setActivePolicyModal("terms")}
                    className="hover:text-zinc-950 transition text-left cursor-pointer"
                  >
                    Điều khoản sử dụng dịch vụ
                  </button>
                </li>
              </ul>
            </div>

            {/* Column 4: Contact Info */}
            <div>
              <h4 className="text-xs font-black text-zinc-950 uppercase tracking-wider mb-2.5">
                Liên Hệ
              </h4>
              <div className="space-y-1.5 text-xs text-zinc-700">
                <p>PickleMatch2K là sản phẩm khóa luận tốt nghiệp, chưa vận hành thương mại.</p>
                <p>Về lịch đặt và hoàn tiền, vui lòng liên hệ trực tiếp cụm sân bạn đã đặt.</p>
              </div>
            </div>
          </div>
        </div>
      </footer>

      {/* Policy Details Modal */}
      {activePolicyModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-zinc-950/60 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white rounded-3xl p-6 sm:p-8 max-w-lg w-full shadow-2xl border border-zinc-200">
            <div className="flex items-center justify-between mb-4 pb-3 border-b border-zinc-100">
              <h3 className="font-black text-base sm:text-lg text-zinc-950">
                {POLICIES_CONTENT[activePolicyModal]?.title}
              </h3>
              <button
                onClick={() => setActivePolicyModal(null)}
                className="w-8 h-8 rounded-full bg-zinc-100 hover:bg-zinc-200 flex items-center justify-center text-zinc-600 font-bold text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="max-h-[60vh] overflow-y-auto pr-1">
              {POLICIES_CONTENT[activePolicyModal]?.content}
            </div>

            <div className="mt-6 pt-3 border-t border-zinc-100 text-right">
              <button
                onClick={() => setActivePolicyModal(null)}
                className="px-5 py-2.5 bg-zinc-950 hover:bg-zinc-800 text-white rounded-xl text-xs sm:text-sm font-bold cursor-pointer transition"
              >
                Đã Hiểu & Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
