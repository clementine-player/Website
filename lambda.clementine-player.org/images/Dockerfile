FROM golang:1.24 AS builder

COPY . /src
WORKDIR /src
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -o /images ./cmd/images

# distroless/static includes the CA certificates needed to call Deezer over HTTPS.
FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=builder /images /server

CMD [ "/server" ]
