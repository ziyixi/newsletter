package service

import (
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"strings"
	"sync"
	"time"
)

// YahooQuote holds the price data returned from Yahoo Finance.
type YahooQuote struct {
	Price     float64
	PrevClose float64
}

// yahooClient handles the cookie/crumb authentication that Yahoo Finance requires.
type yahooClient struct {
	mu     sync.Mutex
	client *http.Client
	crumb  string
	ready  bool
}

var yahoo = &yahooClient{}

const yahooUA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"

func (yc *yahooClient) init() error {
	yc.mu.Lock()
	defer yc.mu.Unlock()
	if yc.ready {
		return nil
	}

	jar, _ := cookiejar.New(nil)
	yc.client = &http.Client{Jar: jar, Timeout: 15 * time.Second}

	// Establish session cookies.
	req, _ := http.NewRequest("GET", "https://fc.yahoo.com/", nil)
	req.Header.Set("User-Agent", yahooUA)
	if resp, err := yc.client.Do(req); err == nil {
		resp.Body.Close()
	}

	// Fetch crumb.
	req, _ = http.NewRequest("GET", "https://query2.finance.yahoo.com/v1/test/getcrumb", nil)
	req.Header.Set("User-Agent", yahooUA)
	resp, err := yc.client.Do(req)
	if err != nil {
		return fmt.Errorf("getting Yahoo crumb: %w", err)
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)

	yc.crumb = string(body)
	yc.ready = true
	return nil
}

// FetchYahooQuote returns price data for a single ticker symbol.
func FetchYahooQuote(symbol string) (*YahooQuote, error) {
	if base := envOrDefault("YAHOO_CHART_BASE", ""); base != "" {
		return fetchChartAtBase(base, symbol)
	}
	if err := yahoo.init(); err != nil {
		return fetchChartDirect(symbol)
	}

	u := fmt.Sprintf(
		"https://query2.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=5d&crumb=%s",
		url.PathEscape(symbol), url.QueryEscape(yahoo.crumb),
	)
	yahoo.mu.Lock()
	c := yahoo.client
	yahoo.mu.Unlock()

	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("User-Agent", yahooUA)
	resp, err := c.Do(req)
	if err != nil || resp.StatusCode != http.StatusOK {
		if resp != nil {
			resp.Body.Close()
		}
		return fetchChartDirect(symbol)
	}
	defer resp.Body.Close()
	return parseChart(resp.Body)
}

func fetchChartAtBase(base, symbol string) (*YahooQuote, error) {
	u := fmt.Sprintf("%s/v8/finance/chart/%s?interval=1d&range=5d",
		strings.TrimSuffix(base, "/"), url.PathEscape(symbol))
	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("User-Agent", yahooUA+" newsletter-bot/1.0")
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		return nil, fmt.Errorf("yahoo chart: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("yahoo chart %d: %s", resp.StatusCode, body)
	}
	return parseChart(resp.Body)
}

func fetchChartDirect(symbol string) (*YahooQuote, error) {
	u := fmt.Sprintf(
		"https://query1.finance.yahoo.com/v8/finance/chart/%s?interval=1d&range=5d",
		url.PathEscape(symbol),
	)
	req, _ := http.NewRequest("GET", u, nil)
	req.Header.Set("User-Agent", yahooUA+" newsletter-bot/1.0")

	resp, err := (&http.Client{Timeout: 15 * time.Second}).Do(req)
	if err != nil {
		return nil, fmt.Errorf("yahoo chart: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("yahoo chart %d: %s", resp.StatusCode, body)
	}
	return parseChart(resp.Body)
}

func parseChart(r io.Reader) (*YahooQuote, error) {
	var data struct {
		Chart struct {
			Result []struct {
				Meta struct {
					RegularMarketPrice float64 `json:"regularMarketPrice"`
					ChartPreviousClose float64 `json:"chartPreviousClose"`
				} `json:"meta"`
			} `json:"result"`
			Error *struct{ Code string } `json:"error"`
		} `json:"chart"`
	}
	if err := json.NewDecoder(r).Decode(&data); err != nil {
		return nil, fmt.Errorf("decoding chart: %w", err)
	}
	if data.Chart.Error != nil {
		return nil, fmt.Errorf("chart error: %s", data.Chart.Error.Code)
	}
	if len(data.Chart.Result) == 0 {
		return nil, fmt.Errorf("no chart results")
	}
	m := data.Chart.Result[0].Meta
	return &YahooQuote{Price: m.RegularMarketPrice, PrevClose: m.ChartPreviousClose}, nil
}
