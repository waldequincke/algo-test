# Stage 1: Build
FROM amazoncorretto:25-alpine AS build
WORKDIR /workspace

COPY . .

# Make sure the wrapper is executable (Alpine sometimes resets permissions)
RUN chmod +x gradlew

# Build
RUN chmod +x gradlew && ./gradlew build -Dquarkus.package.jar.type=fast-jar -x test -x quarkusIntTest

# Stage 2: Create the slim runtime image
FROM amazoncorretto:25-alpine
WORKDIR /deployments

# Copy only the necessary files for the Quarkus Fast-Jar
COPY --from=build /workspace/build/quarkus-app/lib/ /deployments/lib/
COPY --from=build /workspace/build/quarkus-app/*.jar /deployments/
COPY --from=build /workspace/build/quarkus-app/app/ /deployments/app/
COPY --from=build /workspace/build/quarkus-app/quarkus/ /deployments/quarkus/

EXPOSE 8080

# Performance Tuning:
# 1. Use Generational ZGC (or Shenandoah) for sub-millisecond pauses.
# 2. Enable Compact Object Headers to save ~10-20% heap on tree structures.
ENTRYPOINT ["java", \
            "-XX:+UseZGC", \
            "-XX:+UnlockExperimentalVMOptions", \
            "-XX:+UseCompactObjectHeaders", \
            "-Xms512m", \
            "-Xmx512m", \
            "-jar", "/deployments/quarkus-run.jar"]
