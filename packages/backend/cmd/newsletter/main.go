// Binary newsletter fetches content from external services and writes
// a JSON file for the email-service to consume.
//
// Usage:
//
//	go run ./cmd/newsletter                          # writes to .cache/newsletter-data.json
//	go run ./cmd/newsletter -o /tmp/data.json        # custom output path
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"google.golang.org/protobuf/encoding/protojson"

	"newsletter-backend/internal/fetcher"
)

func main() {
	output := flag.String("output", ".cache/newsletter-data.json", "Output JSON path")
	flag.StringVar(output, "o", ".cache/newsletter-data.json", "Output JSON path (shorthand)")
	flag.Parse()

	fmt.Println(strings.Repeat("=", 50))
	fmt.Println("📰  每日简报 — Newsletter Backend")
	fmt.Println(strings.Repeat("=", 50))
	fmt.Println()

	payload := fetcher.FetchAll()

	marshaler := protojson.MarshalOptions{
		EmitUnpopulated: true,
		Indent:          "  ",
	}
	data, err := marshaler.Marshal(payload)
	if err != nil {
		fmt.Fprintf(os.Stderr, "❌  Failed to marshal JSON: %v\n", err)
		os.Exit(1)
	}

	if err := os.MkdirAll(filepath.Dir(*output), 0o755); err != nil {
		fmt.Fprintf(os.Stderr, "❌  Failed to create output dir: %v\n", err)
		os.Exit(1)
	}
	if err := os.WriteFile(*output, data, 0o644); err != nil {
		fmt.Fprintf(os.Stderr, "❌  Failed to write output: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("💾  Data written to %s\n", *output)
}
