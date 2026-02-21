// Package fetcher orchestrates parallel data fetching from all services
// and assembles the final NewsletterPayload proto.
package fetcher

import (
	"fmt"
	"os"
	"strings"
	"sync"
	"time"

	"newsletter-backend/internal/config"
	"newsletter-backend/internal/service"
	pb "newsletter-backend/pb"
)

var weekdaysZH = [...]string{"星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"}

// FetchAll fetches all content sections in parallel, ranks them,
// and returns the assembled NewsletterPayload.
func FetchAll() *pb.NewsletterPayload {
	loc, _ := time.LoadLocation(config.C.Timezone)
	if loc == nil {
		loc = time.UTC
	}
	now := time.Now().In(loc)
	dateStr := fmt.Sprintf("%d年%d月%d日 · %s",
		now.Year(), int(now.Month()), now.Day(),
		weekdaysZH[(int(now.Weekday())+6)%7])

	fmt.Printf("📅  %s\n📬  Recipient: %s\n\n🔄  Fetching content…\n", dateStr, config.C.RecipientName)

	r := fetchParallel()

	// LLM ranking.
	if config.C.RankingEnabled {
		fmt.Println("🏆  Ranking items with LLM …")
		r.news, r.hn = service.RankNews(r.news, r.hn)
		r.arxiv, r.github = service.RankTech(r.arxiv, r.github)
		fmt.Println("  ✅  Ranking complete")
	}

	// Merge astronomy into weather.
	if r.weather == nil {
		r.weather = &pb.WeatherData{}
	}
	if r.astro != nil {
		r.weather.Sunrise = r.astro.Sunrise
		r.weather.Sunset = r.astro.Sunset
		r.weather.DayLength = r.astro.DayLength
		r.weather.GoldenHour = r.astro.GoldenHour
		r.weather.AstroNote = r.astro.Note
	}

	return &pb.NewsletterPayload{
		RecipientName:  config.C.RecipientName,
		Date:           dateStr,
		Weather:        r.weather,
		TopNews:        r.news,
		Stocks:         r.stocks,
		HnStories:      r.hn,
		GithubTrending: r.github,
		ArxivPapers:    r.arxiv,
		ExchangeRates:  r.exchange,
		TodoTasks:      r.todos,
	}
}

// --- parallel fetching ---

type results struct {
	weather  *pb.WeatherData
	astro    *pb.AstronomyData
	news     []*pb.NewsItem
	stocks   []*pb.StockInfo
	hn       []*pb.HNStory
	github   []*pb.GitHubRepo
	arxiv    []*pb.ArxivPaper
	exchange []*pb.ExchangeRate
	todos    []*pb.TodoTask
}

type task struct {
	name string
	fn   func(r *results) error
}

func fetchParallel() *results {
	r := &results{}
	var mu sync.Mutex

	tasks := []task{
		{"weather", func(r *results) error { v, e := service.FetchWeather(); r.weather = v; return e }},
		{"astronomy", func(r *results) error { v, e := service.FetchAstronomy(); r.astro = v; return e }},
		{"news", func(r *results) error { v, e := service.FetchNews(); r.news = v; return e }},
		{"stocks", func(r *results) error { v, e := service.FetchStocks(); r.stocks = v; return e }},
		{"hn", func(r *results) error { v, e := service.FetchHNStories(); r.hn = v; return e }},
		{"github_trending", func(r *results) error { v, e := service.FetchGithubTrending(); r.github = v; return e }},
		{"arxiv", func(r *results) error { v, e := service.FetchArxivPapers(); r.arxiv = v; return e }},
		{"exchange_rates", func(r *results) error { v, e := service.FetchExchangeRates(); r.exchange = v; return e }},
		{"todo_tasks", func(r *results) error { v, e := service.FetchTodoTasks(); r.todos = v; return e }},
	}

	// Filter out skipped services.
	var active []task
	for _, t := range tasks {
		if isSkipped(t.name) {
			fmt.Printf("  ⏭️  %s (skipped via env)\n", t.name)
		} else {
			active = append(active, t)
		}
	}

	var wg sync.WaitGroup
	for _, t := range active {
		wg.Add(1)
		go func(t task) {
			defer wg.Done()
			mu.Lock()
			ref := r
			mu.Unlock()

			if err := t.fn(ref); err != nil {
				fmt.Printf("  ❌  %s: %v\n", t.name, err)
			} else {
				fmt.Printf("  ✅  %s\n", t.name)
			}
		}(t)
	}
	wg.Wait()
	fmt.Println()
	return r
}

func isSkipped(name string) bool {
	v := strings.ToLower(os.Getenv("SKIP_" + strings.ToUpper(name)))
	return v == "true" || v == "1" || v == "yes"
}
