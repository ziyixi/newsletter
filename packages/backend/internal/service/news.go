package service

import (
	"fmt"
	"regexp"
	"strings"

	"github.com/mmcdole/gofeed"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

var sourceMap = map[string]string{
	"BBC News": "BBC News", "BBC News - World": "BBC News",
	"NYT > World News": "New York Times", "The New York Times": "New York Times",
	"Reuters": "Reuters", "Reuters: Top News": "Reuters",
	"CNN.com": "CNN",
	"NPR":     "NPR", "NPR Topics: News": "NPR",
	"Al Jazeera – Breaking News, World News and Video from Al Jazeera": "Al Jazeera",
	"Al Jazeera English": "Al Jazeera",
	"The Guardian":       "The Guardian", "Guardian world news": "The Guardian",
	"The Guardian World": "The Guardian",
}

var htmlTagRe = regexp.MustCompile(`<[^>]+>`)

// FetchNews parses configured RSS feeds and returns translated headlines.
func FetchNews() ([]*pb.NewsItem, error) {
	mult := rankingMultiplier()
	effectiveMax := config.C.NewsMaxItems * mult
	perFeed := max(2, effectiveMax/max(len(config.C.NewsFeeds), 1)+1)

	parser := gofeed.NewParser()
	var all []*pb.NewsItem

	for _, feedURL := range config.C.NewsFeeds {
		feed, err := parser.ParseURL(feedURL)
		if err != nil {
			fmt.Printf("⚠️  Failed to parse feed %s: %v\n", feedURL, err)
			continue
		}
		src := feed.Title
		if mapped, ok := sourceMap[src]; ok {
			src = mapped
		}
		lim := min(perFeed, len(feed.Items))
		for _, item := range feed.Items[:lim] {
			cat := ""
			if len(item.Categories) > 0 {
				cat = item.Categories[0]
			}
			all = append(all, &pb.NewsItem{
				Headline: item.Title,
				Summary:  cleanHTML(item.Description),
				Source:   src,
				Url:      item.Link,
				Category: cat,
			})
		}
	}

	unique := dedup(all, effectiveMax)
	for _, n := range unique {
		n.Headline = TranslateToChinese(n.Headline)
		n.Summary = TranslateToChinese(n.Summary)
		if n.Category != "" {
			n.Category = TranslateToChinese(n.Category)
		}
	}
	return unique, nil
}

func dedup(items []*pb.NewsItem, limit int) []*pb.NewsItem {
	seen := make(map[string]bool)
	var out []*pb.NewsItem
	for _, n := range items {
		key := strings.ToLower(strings.TrimSpace(n.Headline))
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, n)
		if len(out) >= limit {
			break
		}
	}
	return out
}

func cleanHTML(s string) string {
	s = htmlTagRe.ReplaceAllString(s, "")
	for _, pair := range [][2]string{
		{"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"},
		{"&#39;", "'"}, {"&quot;", "\""},
	} {
		s = strings.ReplaceAll(s, pair[0], pair[1])
	}
	s = strings.TrimSpace(s)
	if runes := []rune(s); len(runes) > 200 {
		s = string(runes[:197]) + "…"
	}
	return s
}

func rankingMultiplier() int {
	if config.C.RankingEnabled {
		return config.C.RankingFetchMultiplier
	}
	return 1
}
