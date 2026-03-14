# Build context must be the project root (for gradlew).
# docker build -f kotlin-impl/Dockerfile .

# Stage 1: Build
FROM amazoncorretto:25-alpine AS build
WORKDIR /workspace

COPY . .

RUN chmod +x gradlew && \
    ./gradlew :kotlin-impl:build \
        -Dquarkus.package.jar.type=fast-jar \
        -x test \
        -x quarkusIntTest

# Stage 2: Runtime
FROM amazoncorretto:25-alpine
WORKDIR /deployments

COPY --from=build /workspace/kotlin-impl/build/quarkus-app/lib/     /deployments/lib/
COPY --from=build /workspace/kotlin-impl/build/quarkus-app/*.jar    /deployments/
COPY --from=build /workspace/kotlin-impl/build/quarkus-app/app/     /deployments/app/
COPY --from=build /workspace/kotlin-impl/build/quarkus-app/quarkus/ /deployments/quarkus/

EXPOSE 8081

# Performance tuning:
#   ZGC          → sub-millisecond GC pauses
#   CompactObjectHeaders → ~10-20% heap savings on tree structures (experimental)
ENTRYPOINT ["java", \
            "-XX:+UseZGC", \
            "-XX:+UnlockExperimentalVMOptions", \
            "-XX:+UseCompactObjectHeaders", \
            "-Xms512m", \
            "-Xmx512m", \
            "-Dquarkus.http.port=8081", \
            "-jar", "/deployments/quarkus-run.jar"]
