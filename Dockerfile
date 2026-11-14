FROM golang:1.24-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o /out/node ./cmd/node

FROM alpine:3.20
RUN adduser -D -u 10001 lab
COPY --from=build /out/node /app/node
USER lab
EXPOSE 8080/tcp 9000/udp
ENTRYPOINT ["/app/node"]
