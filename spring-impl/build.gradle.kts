plugins {
    java
    id("org.springframework.boot") version "4.0.3"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "org.example"
version = "1.0.0-SNAPSHOT"

// ── Java 25 toolchain ─────────────────────────────────────────────────────────
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

// ── Belt-and-suspenders: guarantee Tomcat never lands on the classpath ─────────
// spring-boot-starter-webflux does NOT include Tomcat, but this makes the intent
// explicit and guards against transitive pulls from future dependency upgrades.
configurations.all {
    exclude(group = "org.springframework.boot", module = "spring-boot-starter-tomcat")
    exclude(group = "org.springframework.boot", module = "spring-boot-starter-web")
}

dependencies {
    // WebFlux → Netty as embedded server (replaces Tomcat completely)
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    // Health + metrics endpoint  (/actuator/health mirrors Quarkus /q/health)
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // OpenAPI / Swagger UI — webflux variant (mirrors quarkus-smallrye-openapi)
    implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:2.8.3")

    // ── Test ──────────────────────────────────────────────────────────────────
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.withType<Test> {
    useJUnitPlatform()
}
