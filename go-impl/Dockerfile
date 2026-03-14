# Build context: go-impl/
# docker build go-impl/

# ── Stage 1: Build ────────────────────────────────────────────────────────────
FROM golang:1.26-alpine AS build

WORKDIR /app

# Download dependencies first — this layer is cached as long as go.mod/go.sum
# don't change, keeping incremental rebuilds fast.
COPY go.mod go.sum ./
RUN go mod download && go mod verify

COPY main.go ./

# CGO_ENABLED=0  → fully static binary; no libc dependency at runtime.
# -ldflags="-s -w" → strip symbol table (-s) and DWARF debug info (-w);
#                    reduces binary size by ~30% with no runtime impact.
# -trimpath        → remove local filesystem paths from the binary
#                    (reproducible builds, no local path leakage).
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w" -trimpath -o server .

# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
# distroless/static: no shell, no package manager, no libc — only the binary
# and TLS root certificates.
#
# Final image size: ~8 MB vs ~50 MB for alpine (no Go toolchain, no apk index).
# Attack surface: minimal — no shell means no exec-based exploits.
FROM gcr.io/distroless/static-debian12

COPY --from=build /app/server /server

EXPOSE 8086

# GOMAXPROCS: unset — Go 1.21+ automatically reads the container's CFS
# cpu.quota and sets GOMAXPROCS accordingly.  On App Runner (1 vCPU) → 1.
#
# Runtime overrides (match defaults from all other heptathlon implementations):
#   TREE_MAX_DEPTH=500   (max BFS levels)
#   TREE_MAX_NODES=10000 (max total nodes)
#   PORT=8086
ENTRYPOINT ["/server"]
