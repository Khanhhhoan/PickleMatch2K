"use client";

import { useEffect, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

function PaymentsRedirectContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const bookingId = searchParams.get("booking_id");
    if (bookingId) {
      router.replace(`/profile?tab=payments&booking_id=${bookingId}`);
    } else {
      router.replace("/profile?tab=payments");
    }
  }, [router, searchParams]);

  return (
    <div className="min-h-screen bg-zinc-50 flex items-center justify-center font-sans">
      <div className="w-7 h-7 border-2 border-zinc-300 border-t-zinc-950 rounded-full animate-spin" />
    </div>
  );
}

export default function PlayerPaymentsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-zinc-50 flex items-center justify-center font-sans">
          <div className="w-7 h-7 border-2 border-zinc-300 border-t-zinc-950 rounded-full animate-spin" />
        </div>
      }
    >
      <PaymentsRedirectContent />
    </Suspense>
  );
}
