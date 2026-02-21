FROM golang:1.24-alpine AS build
WORKDIR /app
COPY go.mod .
COPY main.go .
COPY fixtures/ fixtures/
RUN go build -o /fake-server .

FROM alpine:3.19
RUN apk add --no-cache ca-certificates curl
WORKDIR /app
COPY --from=build /fake-server .
EXPOSE 8080
ENV FAKE_SERVER_PORT=8080
CMD ["./fake-server"]
