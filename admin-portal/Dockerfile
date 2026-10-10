# Cổng quản trị hệ thống (Next.js). Dùng qua docker-compose.yml ở thư mục gốc.
FROM node:22-slim

ENV NEXT_TELEMETRY_DISABLED=1

WORKDIR /app
RUN chown node:node /app
USER node

# Cài đúng phiên bản đã khóa trong package-lock.json
COPY --chown=node:node package.json package-lock.json ./
RUN npm ci

COPY --chown=node:node . .

# Biến NEXT_PUBLIC_* được nhúng vào mã ngay lúc build (đổi giá trị thì phải build lại).
# Để trống: trình duyệt tự gọi API ở cùng tên máy, cổng 8000.
ARG NEXT_PUBLIC_API_URL=
ARG NEXT_PUBLIC_WS_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL \
    NEXT_PUBLIC_WS_URL=$NEXT_PUBLIC_WS_URL

RUN npm run build

ENV NODE_ENV=production
EXPOSE 3001
CMD ["node", "node_modules/next/dist/bin/next", "start", "-p", "3001"]
