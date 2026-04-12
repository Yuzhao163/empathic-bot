FROM golang:1.21-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download && go mod verify
COPY *.go ./
RUN CGO_ENABLED=0 GOOS=linux go build \
    -ldflags="-s -w" \
    -o gateway .

FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /app
# Add a user for non-root execution
RUN addgroup -S app && adduser -S app -G app
COPY --from=builder /app/gateway .
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
USER app
EXPOSE 8080
CMD ["./gateway"]
