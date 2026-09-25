# --- Construction des deux applications
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
COPY packages/core/package.json packages/core/
COPY apps/web/package.json apps/web/
RUN npm ci --no-audit --no-fund
COPY . .
# Clé Esri pour la vue satellite (facultative) : docker compose build --build-arg VITE_ESRI_TOKEN=...
ARG VITE_ESRI_TOKEN=""
ENV VITE_ESRI_TOKEN=$VITE_ESRI_TOKEN
RUN npm run build

# --- Service statique + relais vers l'API
FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY deploy/security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
EXPOSE 80
