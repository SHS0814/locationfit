FROM node:22-alpine AS build
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node frontend/package*.json ./
RUN npm ci
COPY --chown=node:node frontend/ ./
ARG VITE_API_BASE_URL
ARG VITE_MAP_TILE_URL
ARG VITE_MAP_ATTRIBUTION
RUN npm run build

FROM nginx:1.27-alpine
COPY --chown=nginx:nginx --from=build /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
RUN touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid \
    && chown -R nginx:nginx /var/cache/nginx
USER nginx
EXPOSE 8080
