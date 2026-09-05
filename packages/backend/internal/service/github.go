package service

import (
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"
	"unicode"

	"github.com/PuerkitoBio/goquery"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// FetchGithubTrending scrapes GitHub trending pages for configured languages.
func FetchGithubTrending() ([]*pb.GitHubRepo, error) {
	base := envOrDefault("GITHUB_TRENDING_BASE", "https://github.com") + "/trending"
	perLang := config.C.GithubTrendingMaxPerLang * rankingMultiplier()

	client := &http.Client{Timeout: 15 * time.Second}
	var out []*pb.GitHubRepo

	for _, lang := range config.C.GithubTrendingLanguages {
		u := base
		display := lang
		if lang != "" {
			u = fmt.Sprintf("%s/%s", base, strings.ToLower(lang))
		} else {
			display = "overall"
		}

		req, _ := http.NewRequest("GET", u+"?since=daily", nil)
		req.Header.Set("User-Agent", "Mozilla/5.0 newsletter-bot/1.0")
		resp, err := client.Do(req)
		if err != nil {
			fmt.Printf("⚠️  Failed to fetch GitHub trending for %s: %v\n", display, err)
			continue
		}
		repos := parseTrending(resp.Body, display)
		resp.Body.Close()

		if len(repos) > perLang {
			repos = repos[:perLang]
		}
		out = append(out, repos...)
	}
	return out, nil
}

func parseTrending(r io.Reader, language string) []*pb.GitHubRepo {
	doc, err := goquery.NewDocumentFromReader(r)
	if err != nil {
		return nil
	}
	var repos []*pb.GitHubRepo
	doc.Find("article.Box-row").Each(func(_ int, s *goquery.Selection) {
		a := s.Find("h2 a")
		if a.Length() == 0 {
			return
		}
		name := strings.Join(strings.Fields(strings.TrimSpace(a.Text())), "")
		href, ok := a.Attr("href")
		if !ok {
			return
		}

		desc := ""
		if p := s.Find("p"); p.Length() > 0 {
			desc = strings.TrimSpace(p.Text())
		}

		totalStars := int32(0)
		if sl := s.Find("a.Link--muted.d-inline-block.mr-3"); sl.Length() > 0 {
			totalStars = int32(digits(strings.ReplaceAll(sl.First().Text(), ",", "")))
		}
		todayStars := int32(0)
		if sp := s.Find("span.d-inline-block.float-sm-right"); sp.Length() > 0 {
			parts := strings.Split(sp.Text(), "star")
			if len(parts) > 0 {
				todayStars = int32(digits(parts[0]))
			}
		}

		repos = append(repos, &pb.GitHubRepo{
			Name:        name,
			Description: desc,
			Language:    capitalize(language),
			Stars:       totalStars,
			TodayStars:  todayStars,
			Url:         "https://github.com" + href,
		})
	})
	return repos
}

func digits(s string) int {
	var d []rune
	for _, c := range s {
		if unicode.IsDigit(c) {
			d = append(d, c)
		}
	}
	n, _ := strconv.Atoi(string(d))
	return n
}

func capitalize(s string) string {
	if s == "" {
		return s
	}
	return strings.ToUpper(s[:1]) + s[1:]
}
