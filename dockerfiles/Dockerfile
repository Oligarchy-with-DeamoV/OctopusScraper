FROM golang:1.26.6-bookworm AS builder

ARG VERSION=dev
ARG COMMIT=unknown
ARG BUILD_DATE=unknown

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 GOOS=linux go build \
    -trimpath \
    -ldflags="-s -w \
      -X github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/version.Version=${VERSION} \
      -X github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/version.Commit=${COMMIT} \
      -X github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/version.Date=${BUILD_DATE}" \
    -o /out/runtime/octopus_service \
    ./cmd/octopus_service \
      && mkdir -p /out/runtime/.octopus /out/runtime/resources/scrapers.d

FROM gcr.io/distroless/static-debian12:nonroot

WORKDIR /app

COPY --from=builder --chown=65532:65532 /out/runtime/ /app/

ENV OCTOPUS_TASK_RESULT_PATH=/app/.octopus/task_results.sqlite3

EXPOSE 8000

USER 65532:65532

ENTRYPOINT ["/app/octopus_service"]
CMD ["serve"]
