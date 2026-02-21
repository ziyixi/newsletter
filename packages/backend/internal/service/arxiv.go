package service

import (
	"encoding/xml"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"net/url"
	"strings"
	"time"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

const (
	maxAbstractChars  = 400
	arxivMaxRetries   = 5
	arxivBaseDelay    = 5.0
	arxivDelayBetween = 5 * time.Second
)

// rawPaper holds arXiv data including the full abstract (internal only).
type rawPaper struct {
	proto    *pb.ArxivPaper
	abstract string
}

type atomFeed struct {
	XMLName xml.Name    `xml:"feed"`
	Entries []atomEntry `xml:"entry"`
}
type atomEntry struct {
	ID      string       `xml:"id"`
	Title   string       `xml:"title"`
	Summary string       `xml:"summary"`
	Authors []atomAuthor `xml:"author"`
}
type atomAuthor struct {
	Name string `xml:"name"`
}

// FetchArxivPapers fetches and summarizes arXiv papers for configured queries.
func FetchArxivPapers() ([]*pb.ArxivPaper, error) {
	mult := rankingMultiplier()
	client := &http.Client{Timeout: 30 * time.Second}
	var raws []rawPaper

	for i, q := range config.C.ArxivQueries {
		if i > 0 {
			time.Sleep(arxivDelayBetween)
		}
		raws = append(raws, fetchQueryWithBackoff(client, q, q.MaxResults*mult)...)
	}
	return summarize(raws), nil
}

func fetchQueryWithBackoff(client *http.Client, q config.ArxivQuery, maxResults int) []rawPaper {
	var lastErr error
	for attempt := range arxivMaxRetries {
		u := fmt.Sprintf(
			"http://export.arxiv.org/api/query?search_query=%s&max_results=%d&sortBy=submittedDate&sortOrder=descending",
			url.QueryEscape(q.Query), maxResults,
		)
		resp, err := client.Get(u)
		if err != nil || resp.StatusCode != http.StatusOK {
			if resp != nil {
				resp.Body.Close()
			}
			lastErr = err
			if err == nil {
				lastErr = fmt.Errorf("status %d", resp.StatusCode)
			}
			wait := arxivBaseDelay*intPow(2, attempt) + rand.Float64()
			fmt.Printf("⚠️  arXiv (%s) attempt %d/%d failed: %v — retrying in %.1fs\n",
				q.Label, attempt+1, arxivMaxRetries, lastErr, wait)
			time.Sleep(time.Duration(wait * float64(time.Second)))
			continue
		}

		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()

		var feed atomFeed
		if err := xml.Unmarshal(body, &feed); err != nil {
			lastErr = err
			continue
		}

		var papers []rawPaper
		for _, e := range feed.Entries {
			authors := authorString(e.Authors)
			abs := strings.TrimSpace(strings.ReplaceAll(e.Summary, "\n", " "))
			papers = append(papers, rawPaper{
				proto: &pb.ArxivPaper{
					Title:    strings.TrimSpace(e.Title),
					Authors:  authors,
					Url:      e.ID,
					Category: q.Label,
				},
				abstract: abs,
			})
		}
		return papers
	}
	fmt.Printf("⚠️  Failed to fetch arXiv (%s) after %d attempts: %v\n", q.Label, arxivMaxRetries, lastErr)
	return nil
}

func authorString(authors []atomAuthor) string {
	n := min(3, len(authors))
	names := make([]string, n)
	for i := range n {
		names[i] = authors[i].Name
	}
	s := strings.Join(names, ", ")
	if len(authors) > 3 {
		s += " et al."
	}
	return s
}

// --- summarization ---

func summarize(papers []rawPaper) []*pb.ArxivPaper {
	client := GeminiClient()
	if client != nil {
		return summarizeBatch(papers)
	}
	fmt.Println("⚠️  GEMINI_API_KEY not set — using fallback translation")
	return fallbackAll(papers)
}

func summarizeBatch(papers []rawPaper) []*pb.ArxivPaper {
	if len(papers) == 0 {
		return nil
	}
	client := GeminiClient()
	if client == nil {
		return fallbackAll(papers)
	}

	var lines []string
	for i, p := range papers {
		abs := p.abstract
		if runes := []rune(abs); len(runes) > maxAbstractChars {
			abs = string(runes[:maxAbstractChars])
		}
		lines = append(lines, fmt.Sprintf("[%d] 标题：%s\n    摘要：%s", i, p.proto.Title, abs))
	}

	prompt := "请为以下每篇学术论文提供：\n1. 中文标题翻译\n2. 一句话中文摘要（不超过80字）\n\n" +
		strings.Join(lines, "\n") + "\n\n" +
		"请严格按以下格式逐篇回复，不要多余内容：\n[编号]\n标题：<中文标题>\n摘要：<一句话中文摘要>\n"

	text := GeminiGenerate(client, prompt)
	if text == "" {
		return fallbackAll(papers)
	}
	parseBatch(papers, text)

	out := make([]*pb.ArxivPaper, len(papers))
	for i, p := range papers {
		if p.proto.TitleCn == "" {
			fallbackSingle(&papers[i])
		}
		out[i] = p.proto
	}
	return out
}

func parseBatch(papers []rawPaper, text string) {
	idx := -1
	for _, line := range strings.Split(text, "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		if strings.HasPrefix(line, "[") {
			if end := strings.Index(line, "]"); end > 0 {
				if n, ok := parseDigits(line[1:end]); ok {
					idx = n
				}
			}
			continue
		}
		if idx < 0 || idx >= len(papers) {
			continue
		}
		p := papers[idx].proto
		if val, ok := afterPrefix(line, "标题"); ok {
			p.TitleCn = val
		} else if val, ok := afterPrefix(line, "摘要"); ok {
			p.Summary = val
		}
	}
}

func afterPrefix(line, prefix string) (string, bool) {
	for _, sep := range []string{"：", ":"} {
		full := prefix + sep
		if strings.HasPrefix(line, full) {
			return strings.TrimSpace(line[len(full):]), true
		}
	}
	return "", false
}

func fallbackAll(papers []rawPaper) []*pb.ArxivPaper {
	out := make([]*pb.ArxivPaper, len(papers))
	for i := range papers {
		fallbackSingle(&papers[i])
		out[i] = papers[i].proto
	}
	return out
}

func fallbackSingle(p *rawPaper) {
	if p.proto.TitleCn == "" {
		p.proto.TitleCn = TranslateToChinese(p.proto.Title)
	}
	if p.proto.Summary == "" {
		runes := []rune(p.abstract)
		if len(runes) > 150 {
			p.proto.Summary = string(runes[:150]) + "…"
		} else {
			p.proto.Summary = p.abstract
		}
	}
}

func parseDigits(s string) (int, bool) {
	s = strings.TrimSpace(s)
	n := 0
	for _, c := range s {
		if c < '0' || c > '9' {
			return 0, false
		}
		n = n*10 + int(c-'0')
	}
	return n, len(s) > 0
}
