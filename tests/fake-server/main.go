// Fake server mocks all external APIs for newsletter integration tests.
// Usage: go run .  (listens on port 8080, or FAKE_SERVER_PORT)
package main

import (
	"embed"
	"encoding/json"
	"fmt"
	"io/fs"
	"log"
	"net/http"
	"os"
	"path"
	"strings"
)

//go:embed fixtures
var fixturesFS embed.FS

const defaultPort = "8080"

func main() {
	port := os.Getenv("FAKE_SERVER_PORT")
	if port == "" {
		port = defaultPort
	}
	fixtures, _ := fs.Sub(fixturesFS, "fixtures")
	http.HandleFunc("/", handler(fixtures))
	addr := "0.0.0.0:" + port
	log.Printf("Fake server listening on %s", addr)
	if err := http.ListenAndServe(addr, nil); err != nil {
		log.Fatal(err)
	}
}

func handler(fixtures fs.FS) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		pathOnly := path.Clean(r.URL.Path)
		if r.URL.RawQuery != "" {
			pathOnly = strings.Split(r.URL.Path, "?")[0]
		}

		// Translate API: echo back the "q" param as translated text
		if strings.HasPrefix(pathOnly, "/translate_a/") {
			q := r.URL.Query().Get("q")
			// Response format: [[["translated","original",null,null,3]],...]
			body := fmt.Sprintf("[[[\"%s\",\"%s\",null,null,3]]]", escapeJSON(q), escapeJSON(q))
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			w.Write([]byte(body))
			return
		}

		// Route to fixture file
		fixture, contentType := route(pathOnly)
		if fixture == "" {
			if pathOnly == "/health" {
				w.WriteHeader(http.StatusOK)
				w.Write([]byte("OK"))
				return
			}
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusNotFound)
			w.Write([]byte(`{"error":"Unknown path: ` + pathOnly + `"}`))
			return
		}

		data, err := fs.ReadFile(fixtures, fixture)
		if err != nil {
			w.WriteHeader(http.StatusInternalServerError)
			w.Write([]byte(err.Error()))
			return
		}
		w.Header().Set("Content-Type", contentType)
		w.WriteHeader(http.StatusOK)
		w.Write(data)
	}
}

func route(pathOnly string) (fixture string, contentType string) {
	routes := map[string][2]string{
		"/v1/forecast":        {"weather.json", "application/json"},
		"/v0/topstories.json": {"hn_topstories.json", "application/json"},
		"/v0/item/1.json":     {"hn_item_1.json", "application/json"},
		"/v0/item/2.json":     {"hn_item_2.json", "application/json"},
		"/v0/item/3.json":     {"hn_item_3.json", "application/json"},
		"/v0/item/4.json":     {"hn_item_4.json", "application/json"},
		"/v0/item/5.json":     {"hn_item_5.json", "application/json"},
		"/trending":           {"github_trending.html", "text/html"},
		"/trending/python":    {"github_trending.html", "text/html"},
		"/trending/go":        {"github_trending.html", "text/html"},
		"/trending/rust":      {"github_trending.html", "text/html"},
		"/api/recommendation": {"todo.json", "application/json"},
		"/rss/feed":           {"rss_feed.xml", "application/xml"},
		"/api/query":          {"arxiv_query.xml", "application/atom+xml"},
	}
	if p, ok := routes[pathOnly]; ok {
		return p[0], p[1]
	}
	// Yahoo chart: /v8/finance/chart/AAPL or /v8/finance/chart/USDCNY%3DX
	if strings.HasPrefix(pathOnly, "/v8/finance/chart/") {
		return "yahoo_chart.json", "application/json"
	}
	return "", ""
}

func escapeJSON(s string) string {
	b, _ := json.Marshal(s)
	return strings.Trim(string(b), `"`)
}
