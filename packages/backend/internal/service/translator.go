package service

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"time"
)

var translateHTTP = &http.Client{Timeout: 10 * time.Second}

// TranslateToChinese translates text to Simplified Chinese via the free
// Google Translate API. Returns the original text on failure.
func TranslateToChinese(text string) string {
	if text == "" {
		return text
	}

	u := fmt.Sprintf(
		"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=zh-CN&dt=t&q=%s",
		url.QueryEscape(text),
	)

	resp, err := translateHTTP.Get(u)
	if err != nil {
		return text
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return text
	}

	// Response is a nested JSON array: [[["translated","original",...],...],...].
	var result []any
	if err := json.Unmarshal(body, &result); err != nil {
		return text
	}
	if t := extractTranslation(result); t != "" {
		return t
	}
	return text
}

func extractTranslation(data []any) string {
	if len(data) == 0 {
		return ""
	}
	sentences, ok := data[0].([]any)
	if !ok {
		return ""
	}
	var out string
	for _, s := range sentences {
		parts, ok := s.([]any)
		if !ok || len(parts) == 0 {
			continue
		}
		if t, ok := parts[0].(string); ok {
			out += t
		}
	}
	return out
}
