"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function RedirectToVenues() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/owner/venues");
  }, [router]);

  return (
    <div className="p-8 text-center text-xs text-zinc-500 font-sans">
      Đang chuyển tiếp về Cài Đặt Cụm Sân...
    </div>
  );
}
