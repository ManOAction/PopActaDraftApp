# Build the frontend
FROM oven/bun:latest AS builder
WORKDIR /app
COPY frontend .
RUN bun install
RUN bun run build

# Create the nginx image with built frontend
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/nginx.conf