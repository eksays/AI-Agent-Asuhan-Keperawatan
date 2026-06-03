# Frontend Next.js — image produksi multi-stage, berjalan sebagai user NON-ROOT (anti-root).
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-slim
ENV NODE_ENV=production
WORKDIR /app
COPY --from=build /app ./

# Anti-root: jalankan Next.js dengan hak akses terbatas.
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 3000
CMD ["npm", "run", "start"]
