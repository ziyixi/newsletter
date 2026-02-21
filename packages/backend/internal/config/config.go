// Package config loads the newsletter configuration from
// newsletter.config.yaml with environment variable overrides.
package config

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/joho/godotenv"
	"gopkg.in/yaml.v3"
)

// ArxivQuery defines a single arXiv search query from the config.
type ArxivQuery struct {
	Query      string `yaml:"query"`
	Label      string `yaml:"label"`
	MaxResults int    `yaml:"maxResults"`
}

// Config holds all newsletter backend settings.
type Config struct {
	RecipientEmail string
	RecipientName  string

	WeatherLat          float64
	WeatherLon          float64
	WeatherLocationName string

	NewsFeeds    []string
	NewsMaxItems int

	StockSymbols []string
	StockNames   map[string]string

	HNMaxStories int
	Timezone     string

	GithubTrendingLanguages  []string
	GithubTrendingMaxPerLang int

	ArxivQueries []ArxivQuery
	GeminiModel  string

	RankingEnabled         bool
	RankingFetchMultiplier int

	ExchangeRatePairs []string
	ExchangeRateNames map[string]string

	TodoAPIUser     string
	TodoAPIPassword string
}

// C is the singleton configuration instance, populated at init time.
var C *Config

func init() {
	var err error
	C, err = load()
	if err != nil {
		fmt.Fprintf(os.Stderr, "⚠️  Failed to load config: %v\n", err)
		C = defaults()
	}
}

// --- YAML mapping types ---

type rawConfig struct {
	Recipient struct {
		Name  string `yaml:"name"`
		Email string `yaml:"email"`
	} `yaml:"recipient"`
	Schedule struct {
		Timezone string `yaml:"timezone"`
	} `yaml:"schedule"`
	Weather struct {
		Latitude  *float64 `yaml:"latitude"`
		Longitude *float64 `yaml:"longitude"`
		Location  string   `yaml:"location"`
	} `yaml:"weather"`
	News struct {
		MaxItems int      `yaml:"maxItems"`
		Feeds    []string `yaml:"feeds"`
	} `yaml:"news"`
	Stocks struct {
		Symbols []string          `yaml:"symbols"`
		Names   map[string]string `yaml:"names"`
	} `yaml:"stocks"`
	HackerNews struct {
		MaxStories int `yaml:"maxStories"`
	} `yaml:"hackerNews"`
	GithubTrending struct {
		Languages      []string `yaml:"languages"`
		MaxPerLanguage int      `yaml:"maxPerLanguage"`
	} `yaml:"githubTrending"`
	Arxiv struct {
		GeminiModel string       `yaml:"geminiModel"`
		Queries     []ArxivQuery `yaml:"queries"`
	} `yaml:"arxiv"`
	Ranking struct {
		Enabled         bool `yaml:"enabled"`
		FetchMultiplier int  `yaml:"fetchMultiplier"`
	} `yaml:"ranking"`
	ExchangeRates struct {
		Pairs []string          `yaml:"pairs"`
		Names map[string]string `yaml:"names"`
	} `yaml:"exchangeRates"`
}

// --- loaders ---

func load() (*Config, error) {
	path := configPath()
	_ = godotenv.Load(filepath.Join(filepath.Dir(path), ".env"))

	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading config %s: %w", path, err)
	}
	var raw rawConfig
	if err := yaml.Unmarshal(data, &raw); err != nil {
		return nil, fmt.Errorf("parsing config: %w", err)
	}
	return build(raw), nil
}

func build(raw rawConfig) *Config {
	return &Config{
		RecipientEmail: envOr("RECIPIENT_EMAIL", raw.Recipient.Email, "you@example.com"),
		RecipientName:  envOr("RECIPIENT_NAME", raw.Recipient.Name, "Ziyi"),

		WeatherLat:          envFloatOpt("WEATHER_LAT", raw.Weather.Latitude, 37.3688),
		WeatherLon:          envFloatOpt("WEATHER_LON", raw.Weather.Longitude, -122.0363),
		WeatherLocationName: envOr("WEATHER_LOCATION", raw.Weather.Location, "圣尼维尔，加州"),

		NewsFeeds:    envCSV("NEWS_FEEDS", raw.News.Feeds),
		NewsMaxItems: envInt("NEWS_MAX_ITEMS", raw.News.MaxItems, 5),

		StockSymbols: envCSV("STOCK_SYMBOLS", raw.Stocks.Symbols),
		StockNames:   mapOr(raw.Stocks.Names),

		HNMaxStories: envInt("HN_MAX_STORIES", raw.HackerNews.MaxStories, 5),
		Timezone:     envOr("TIMEZONE", raw.Schedule.Timezone, "America/Los_Angeles"),

		GithubTrendingLanguages:  sliceOr(raw.GithubTrending.Languages, []string{"python", "go", "rust"}),
		GithubTrendingMaxPerLang: intOr(raw.GithubTrending.MaxPerLanguage, 3),

		ArxivQueries: arxivQueriesOr(raw.Arxiv.Queries),
		GeminiModel:  strOr(raw.Arxiv.GeminiModel, "gemini-2.0-flash"),

		RankingEnabled:         envBool("RANKING_ENABLED", raw.Ranking.Enabled),
		RankingFetchMultiplier: envInt("RANKING_FETCH_MULTIPLIER", raw.Ranking.FetchMultiplier, 3),

		ExchangeRatePairs: sliceOr(raw.ExchangeRates.Pairs, []string{"USD/CNY"}),
		ExchangeRateNames: mapOr(raw.ExchangeRates.Names),

		TodoAPIUser:     os.Getenv("TODO_API_USER"),
		TodoAPIPassword: os.Getenv("TODO_API_PASSWORD"),
	}
}

func defaults() *Config {
	return &Config{
		RecipientEmail:           "you@example.com",
		RecipientName:            "Ziyi",
		WeatherLat:               37.3688,
		WeatherLon:               -122.0363,
		WeatherLocationName:      "圣尼维尔，加州",
		NewsMaxItems:             5,
		HNMaxStories:             5,
		Timezone:                 "America/Los_Angeles",
		GithubTrendingLanguages:  []string{"python", "go", "rust"},
		GithubTrendingMaxPerLang: 3,
		GeminiModel:              "gemini-2.0-flash",
		RankingFetchMultiplier:   3,
		ExchangeRatePairs:        []string{"USD/CNY"},
		StockNames:               map[string]string{},
		ExchangeRateNames:        map[string]string{},
	}
}

// --- helpers ---

func configPath() string {
	if p := os.Getenv("NEWSLETTER_CONFIG_PATH"); p != "" {
		return p
	}
	for _, c := range []string{"newsletter.config.yaml", "../../newsletter.config.yaml"} {
		if _, err := os.Stat(c); err == nil {
			return c
		}
	}
	return "../../newsletter.config.yaml"
}

func envOr(key, yaml, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	if yaml != "" {
		return yaml
	}
	return fallback
}

func envInt(key string, yaml, fallback int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return intOr(yaml, fallback)
}

// envFloatOpt uses env override, then yaml if present (including 0), else fallback.
// Use for values where 0 is valid (e.g. latitude/longitude at equator/prime meridian).
func envFloatOpt(key string, yaml *float64, fallback float64) float64 {
	if v := os.Getenv(key); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	if yaml != nil {
		return *yaml
	}
	return fallback
}

func envBool(key string, yaml bool) bool {
	if v := os.Getenv(key); v != "" {
		v = strings.ToLower(v)
		return v == "true" || v == "1" || v == "yes"
	}
	return yaml
}

func envCSV(key string, yaml []string) []string {
	if v := os.Getenv(key); v != "" {
		var out []string
		for _, p := range strings.Split(v, ",") {
			if p = strings.TrimSpace(p); p != "" {
				out = append(out, p)
			}
		}
		if len(out) > 0 {
			return out
		}
	}
	return yaml
}

func strOr(v, fallback string) string {
	if v != "" {
		return v
	}
	return fallback
}

func intOr(v, fallback int) int {
	if v != 0 {
		return v
	}
	return fallback
}

func sliceOr(v, fallback []string) []string {
	if len(v) > 0 {
		return v
	}
	return fallback
}

func mapOr(v map[string]string) map[string]string {
	if v == nil {
		return map[string]string{}
	}
	return v
}

func arxivQueriesOr(v []ArxivQuery) []ArxivQuery {
	if len(v) > 0 {
		for i := range v {
			if v[i].MaxResults == 0 {
				v[i].MaxResults = 3
			}
		}
		return v
	}
	return []ArxivQuery{
		{Query: "cat:cs.CL AND abs:LLM", Label: "LLM", MaxResults: 3},
		{Query: "cat:cs.DC AND abs:HPC", Label: "HPC", MaxResults: 2},
	}
}
