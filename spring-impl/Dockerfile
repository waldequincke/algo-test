# Build context: spring-impl/
# docker build spring-impl/

# Stage 1: Build
FROM amazoncorretto:25-alpine AS build
WORKDIR /workspace

COPY build.gradle.kts settings.gradle.kts gradlew ./
COPY gradle ./gradle
RUN chmod +x gradlew

# Resolve dependencies first (Docker layer cache)
RUN ./gradlew dependencies --no-daemon -q 2>/dev/null || true

COPY src ./src
RUN ./gradlew bootJar -x test --no-daemon

# Stage 2: Runtime
FROM amazoncorretto:25-alpine
WORKDIR /app

COPY --from=build /workspace/build/libs/*.jar app.jar

EXPOSE 8084

# Performance tuning — mirrors java-impl Dockerfile:
#   ZGC              → sub-millisecond GC pauses
#   CompactObjectHeaders → ~10-20% heap savings on tree structures (experimental)
ENTRYPOINT ["java", \
            "-XX:+UseZGC", \
            "-XX:+UnlockExperimentalVMOptions", \
            "-XX:+UseCompactObjectHeaders", \
            "-Xms512m", \
            "-Xmx512m", \
            "-jar", "/app/app.jar"]
