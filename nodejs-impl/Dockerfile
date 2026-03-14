# Build context: nodejs-impl/
# docker build nodejs-impl/

# Stage 1: Build
FROM node:24-alpine AS build
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY nest-cli.json tsconfig*.json ./
COPY src ./src
RUN npm run build

# Stage 2: Runtime (production deps only)
FROM node:24-alpine
WORKDIR /app

COPY package*.json ./
RUN npm ci --omit=dev

COPY --from=build /app/dist ./dist

EXPOSE 8082

CMD ["node", "dist/main"]
