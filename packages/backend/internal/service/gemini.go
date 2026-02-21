// Package service implements individual data-fetching services.
package service

import (
	"context"
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"google.golang.org/genai"

	"newsletter-backend/internal/config"
)

const (
	geminiMinCallGap  = 1 * time.Second
	geminiMaxRetries  = 2
	geminiBackoffBase = 2.0
)

var fallbackModels = []string{"gemini-2.5-flash", "gemini-2.5-flash-lite"}

var (
	geminiOnce   sync.Once
	geminiClient *genai.Client
	lastCallMu   sync.Mutex
	lastCallTS   time.Time
)

// GeminiClient returns a shared Gemini client, or nil if GEMINI_API_KEY is unset.
func GeminiClient() *genai.Client {
	geminiOnce.Do(func() {
		key := os.Getenv("GEMINI_API_KEY")
		if key == "" {
			return
		}
		c, err := genai.NewClient(context.Background(), &genai.ClientConfig{
			APIKey:  key,
			Backend: genai.BackendGeminiAPI,
		})
		if err != nil {
			fmt.Fprintf(os.Stderr, "⚠️  Failed to create Gemini client: %v\n", err)
			return
		}
		geminiClient = c
	})
	return geminiClient
}

// GeminiGenerate calls Gemini with model fallback, retry, and rate-limiting.
// Returns the trimmed response text, or "" if every attempt fails.
func GeminiGenerate(client *genai.Client, prompt string) string {
	models := append([]string{config.C.GeminiModel}, fallbackModels...)

	for _, model := range models {
		for attempt := range geminiMaxRetries + 1 {
			waitForRateLimit()

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			resp, err := client.Models.GenerateContent(ctx, model, genai.Text(prompt), nil)
			cancel()
			recordCall()

			if err == nil {
				if t := strings.TrimSpace(resp.Text()); t != "" {
					return t
				}
			}

			wait := time.Duration(intPow(geminiBackoffBase, attempt)) * time.Second
			fmt.Fprintf(os.Stderr, "⚠️  Gemini (%s) attempt %d failed: %v\n", model, attempt+1, err)
			if attempt < geminiMaxRetries {
				time.Sleep(wait)
			}
		}
	}
	return ""
}

func waitForRateLimit() {
	lastCallMu.Lock()
	elapsed := time.Since(lastCallTS)
	lastCallMu.Unlock()
	if elapsed < geminiMinCallGap {
		time.Sleep(geminiMinCallGap - elapsed)
	}
}

func recordCall() {
	lastCallMu.Lock()
	lastCallTS = time.Now()
	lastCallMu.Unlock()
}

func intPow(base float64, exp int) float64 {
	r := 1.0
	for range exp {
		r *= base
	}
	return r
}
