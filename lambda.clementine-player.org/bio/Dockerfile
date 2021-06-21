FROM golang:1.16 AS builder

COPY . /src
WORKDIR /src
RUN CGO_ENABLED=0 GOOS=linux go build -a -ldflags '-extldflags "-static"' ./cmd/bio

FROM alpine:3.14
RUN apk add --no-cache ca-certificates

COPY --from=builder /src/bio /server

CMD [ "/server" ]