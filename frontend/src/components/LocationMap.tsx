"use client";

import { useEffect, useRef, useState } from "react";
import type { LayerGroup, Map as LeafletMap, Marker } from "leaflet";
import "leaflet/dist/leaflet.css";

export interface MapVenue {
  id: number;
  name: string;
  lat: number;
  lng: number;
}

interface LocationMapProps {
  /** Điểm đang chọn; null khi chưa chọn */
  value: { lat: number; lng: number } | null;
  /** Các cụm sân của hệ thống, hiện thành chấm xanh để người dùng biết sân nằm đâu */
  venues: MapVenue[];
  /** Bấm lên bản đồ, kéo ghim, hoặc bấm vào chấm của một cụm sân (khi đó có venueName) */
  onPick: (lat: number, lng: number, venueName?: string) => void;
}

const HCM_CENTER: [number, number] = [10.7769, 106.7009];

const PIN_HTML =
  '<div style="width:18px;height:18px;border-radius:9999px;background:#18181b;border:3px solid #fff;box-shadow:0 1px 6px rgba(0,0,0,.45)"></div>';

/** Bản đồ OpenStreetMap trong hộp chọn vị trí. Leaflet chỉ chạy trên trình duyệt nên được nạp khi bản đồ hiện ra. */
export default function LocationMap({ value, venues, onPick }: LocationMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const leafletRef = useRef<typeof import("leaflet") | null>(null);
  const mapRef = useRef<LeafletMap | null>(null);
  const pinRef = useRef<Marker | null>(null);
  const venueLayerRef = useRef<LayerGroup | null>(null);
  const fittedRef = useRef(false);
  const onPickRef = useRef(onPick);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    onPickRef.current = onPick;
  });

  useEffect(() => {
    let cancelled = false;
    import("leaflet").then((module) => {
      const L = module.default;
      if (cancelled || !containerRef.current || mapRef.current) return;
      const map = L.map(containerRef.current, { center: HCM_CENTER, zoom: 12, scrollWheelZoom: true });
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      }).addTo(map);
      map.on("click", (event) => onPickRef.current(event.latlng.lat, event.latlng.lng));
      venueLayerRef.current = L.layerGroup().addTo(map);
      leafletRef.current = L;
      mapRef.current = map;
      // Hộp thoại vừa mở có thể chưa có kích thước cuối cùng lúc bản đồ được tạo
      window.setTimeout(() => map.invalidateSize(), 150);
      setReady(true);
    });
    return () => {
      cancelled = true;
      mapRef.current?.remove();
      mapRef.current = null;
      pinRef.current = null;
      venueLayerRef.current = null;
    };
  }, []);

  const lat = value?.lat;
  const lng = value?.lng;
  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    if (!ready || !L || !map) return;
    if (lat === undefined || lng === undefined) {
      pinRef.current?.remove();
      pinRef.current = null;
      return;
    }
    if (!pinRef.current) {
      const icon = L.divIcon({ html: PIN_HTML, className: "", iconSize: [18, 18], iconAnchor: [9, 9] });
      pinRef.current = L.marker([lat, lng], { icon, draggable: true, zIndexOffset: 1000 }).addTo(map);
      pinRef.current.on("dragend", (event) => {
        const point = (event.target as Marker).getLatLng();
        onPickRef.current(point.lat, point.lng);
      });
    } else {
      pinRef.current.setLatLng([lat, lng]);
    }
    if (!map.getBounds().pad(-0.1).contains([lat, lng])) map.panTo([lat, lng]);
  }, [ready, lat, lng]);

  useEffect(() => {
    const L = leafletRef.current;
    const map = mapRef.current;
    const layer = venueLayerRef.current;
    if (!ready || !L || !map || !layer) return;
    layer.clearLayers();
    venues.forEach((venue) => {
      // bubblingMouseEvents: false - bấm vào chấm sân thì bản đồ không nhận thêm cú bấm "điểm bất kỳ" đè lên
      L.circleMarker([venue.lat, venue.lng], {
        radius: 8, color: "#fff", weight: 2, fillColor: "#2563eb", fillOpacity: 0.95, bubblingMouseEvents: false,
      })
        .bindTooltip(venue.name, { direction: "top", offset: [0, -6] })
        .on("click", () => onPickRef.current(venue.lat, venue.lng, venue.name))
        .addTo(layer);
    });
    // Lần đầu có danh sách sân: canh khung nhìn vừa đủ mọi cụm sân và điểm đang chọn. Đợi hộp thoại hiện xong
    // (có hiệu ứng mở) để bản đồ biết đúng kích thước của nó, nhất là trên điện thoại.
    if (!fittedRef.current && venues.length > 0) {
      fittedRef.current = true;
      window.setTimeout(() => {
        if (mapRef.current !== map) return;
        const points: [number, number][] = venues.map((venue) => [venue.lat, venue.lng]);
        const pin = pinRef.current?.getLatLng();
        if (pin) points.push([pin.lat, pin.lng]);
        map.invalidateSize();
        map.fitBounds(L.latLngBounds(points), { padding: [28, 28], maxZoom: 14 });
      }, 250);
    }
  }, [ready, venues]);

  return <div ref={containerRef} className="h-60 w-full rounded-xl border border-zinc-200 overflow-hidden z-0" />;
}
