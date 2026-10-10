import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { AuthProvider } from "@/lib/auth-context";
import PlayerBottomNav from "@/components/PlayerBottomNav";
import { ToastProvider } from "@/components/Toast";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin", "vietnamese"],
});

export const metadata: Metadata = {
  title: "PickleMatch2K - Nền Tảng Đặt Sân & Ghép Trận Pickleball Thông Minh",
  description: "Hệ thống chuyên biệt: Đặt sân & ghép trận, Chủ sân quản lý doanh thu, Quản trị viên giám sát toàn diện.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  userScalable: false,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi" className={`${inter.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col font-sans bg-zinc-50/50 text-zinc-900 selection:bg-zinc-900 selection:text-zinc-50">
        <ToastProvider>
          <AuthProvider>
            <div className="flex-1 flex flex-col pb-16 md:pb-0">
              {children}
            </div>
            <PlayerBottomNav />
          </AuthProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
