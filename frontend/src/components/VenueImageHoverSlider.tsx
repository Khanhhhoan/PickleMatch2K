"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import { getMediaUrl } from "@/lib/api";

interface VenueImageHoverSliderProps {
  venue: {
    id: number;
    name: string;
    image_url?: string | null;
    images?: string | string[] | null;
    courts?: any[];
    distance_km?: number | null;
  };
  className?: string;
  showBadges?: boolean;
  showDistance?: boolean;
  /** Thứ hạng khi danh sách xếp theo "Phù hợp nhất" (1 = phù hợp nhất); không truyền thì không hiện. */
  rank?: number;
}

export default function VenueImageHoverSlider({
  venue,
  className = "h-48 sm:h-56",
  showBadges = true,
  showDistance = true,
  rank,
}: VenueImageHoverSliderProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isHovered, setIsHovered] = useState(false);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  // Extract and compile all images
  const imageList = useMemo(() => {
    const list: string[] = [];

    // 1. Primary image if set
    if (venue.image_url) {
      list.push(getMediaUrl(venue.image_url));
    }

    // 2. Parse gallery images
    if (venue.images) {
      let parsed: string[] = [];
      if (typeof venue.images === "string") {
        try {
          parsed = JSON.parse(venue.images);
        } catch {
          parsed = [];
        }
      } else if (Array.isArray(venue.images)) {
        parsed = venue.images;
      }

      if (Array.isArray(parsed)) {
        parsed.forEach((img) => {
          const url = getMediaUrl(img);
          if (url && !list.includes(url)) {
            list.push(url);
          }
        });
      }
    }

    // 3. Cụm sân chưa tải ảnh: dùng ảnh nền trung tính, không mượn ảnh của nơi khác
    if (list.length === 0) {
      list.push("/images/hero_bg.jpg");
    }

    return list;
  }, [venue.image_url, venue.images]);

  // Handle auto-cycle on hover
  useEffect(() => {
    if (isHovered && imageList.length > 1) {
      timerRef.current = setInterval(() => {
        setCurrentIndex((prev) => (prev + 1) % imageList.length);
      }, 1600); // Transitions every 1.6s on hover
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      // Reset back to primary cover image smoothly
      setCurrentIndex(0);
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [isHovered, imageList.length]);

  const handlePrev = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev - 1 + imageList.length) % imageList.length);
  };

  const handleNext = (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex((prev) => (prev + 1) % imageList.length);
  };

  const handleDotClick = (e: React.MouseEvent, idx: number) => {
    e.preventDefault();
    e.stopPropagation();
    setCurrentIndex(idx);
  };

  return (
    <div
      className={`relative w-full overflow-hidden bg-zinc-950 select-none ${className}`}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {/* Slides (Stacked Images for Cross-Fade Animation) */}
      {imageList.map((imgUrl, idx) => (
        <div
          key={idx}
          className={`absolute inset-0 transition-opacity duration-700 ease-in-out ${
            idx === currentIndex ? "opacity-100 z-0" : "opacity-0 pointer-events-none"
          }`}
        >
          <img
            src={imgUrl}
            alt={`${venue.name} - Ảnh ${idx + 1}`}
            className="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-700 ease-out"
            onError={(e: any) => {
              e.currentTarget.src = "/images/hero_bg.jpg";
            }}
          />
        </div>
      ))}

      {/* Dark Vignette Overlay for Readability */}
      <div className="absolute inset-0 bg-gradient-to-t from-zinc-950/85 via-zinc-950/20 to-transparent pointer-events-none" />

      {/* Segmented Top Progress Bars (Instagram / Airbnb Style) */}
      {imageList.length > 1 && (
        <div className="absolute top-2.5 left-3 right-3 z-20 flex items-center gap-1.5 pointer-events-auto">
          {imageList.map((_, idx) => (
            <button
              key={idx}
              type="button"
              onClick={(e) => handleDotClick(e, idx)}
              className="flex-1 h-1 rounded-full overflow-hidden bg-white/30 backdrop-blur-xs transition-all cursor-pointer hover:h-1.5"
              title={`Ảnh ${idx + 1}/${imageList.length}`}
            >
              <div
                className={`h-full transition-all duration-300 ${
                  idx === currentIndex
                    ? "bg-white w-full shadow-xs"
                    : idx < currentIndex && isHovered
                    ? "bg-white/70 w-full"
                    : "w-0"
                }`}
              />
            </button>
          ))}
        </div>
      )}

      {/* Badges on Image */}
      {showBadges && (
        <div className="absolute top-5 left-3 z-10 flex items-center gap-1.5 flex-wrap pointer-events-none">
          {rank !== undefined && (
            <span
              className={`px-2.5 py-1 rounded-xl text-[11px] font-black shadow-xs ${
                rank === 1 ? "bg-amber-400 text-zinc-950" : "bg-white/95 text-zinc-950 border border-zinc-200"
              }`}
            >
              Top {rank}
            </span>
          )}
          <span className="px-2.5 py-1 rounded-xl bg-zinc-950/80 backdrop-blur-md text-white text-[11px] font-black shadow-xs border border-white/10">
            {venue.courts?.length || 0} sân thi đấu
          </span>
          <span className="px-2.5 py-1 rounded-xl bg-emerald-500/90 backdrop-blur-md text-white text-[11px] font-bold shadow-xs">
            Đang hoạt động
          </span>
        </div>
      )}

      {/* Distance Badge */}
      {showDistance && venue.distance_km !== null && venue.distance_km !== undefined && (
        <div className="absolute top-5 right-3 z-10 pointer-events-none">
          <span className="text-xs font-black text-zinc-900 bg-white/95 backdrop-blur-md px-3 py-1 rounded-xl shadow-xs border border-zinc-200">
            {venue.distance_km.toFixed(1)} km
          </span>
        </div>
      )}

      {/* Left / Right Arrow Buttons on Hover */}
      {imageList.length > 1 && (
        <div
          className={`absolute inset-y-0 left-0 right-0 z-20 flex items-center justify-between px-2 transition-opacity duration-200 ${
            isHovered ? "opacity-100" : "opacity-0 pointer-events-none"
          }`}
        >
          <button
            type="button"
            onClick={handlePrev}
            className="w-8 h-8 rounded-full bg-zinc-950/70 hover:bg-zinc-950 text-white backdrop-blur-md flex items-center justify-center text-sm font-black shadow-lg transition-transform active:scale-95 cursor-pointer border border-white/20"
            title="Ảnh trước"
          >
            ‹
          </button>
          <button
            type="button"
            onClick={handleNext}
            className="w-8 h-8 rounded-full bg-zinc-950/70 hover:bg-zinc-950 text-white backdrop-blur-md flex items-center justify-center text-sm font-black shadow-lg transition-transform active:scale-95 cursor-pointer border border-white/20"
            title="Ảnh tiếp theo"
          >
            ›
          </button>
        </div>
      )}

      {/* Bottom Title & Image Counter */}
      <div className="absolute bottom-3 left-4 right-4 z-10 flex items-end justify-between gap-2 pointer-events-none">
        <h3 className="text-lg sm:text-xl font-black text-white drop-shadow-md line-clamp-1 flex-1">
          {venue.name}
        </h3>

        {imageList.length > 1 && (
          <span className="text-[10px] font-bold text-zinc-200 bg-zinc-950/75 backdrop-blur-md px-2 py-0.5 rounded-md shrink-0 border border-white/10">
            {currentIndex + 1}/{imageList.length}
          </span>
        )}
      </div>
    </div>
  );
}
