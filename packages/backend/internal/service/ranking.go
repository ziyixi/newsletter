package service

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// RankNews ranks and trims news + HN stories using Gemini.
// Returns the original slices (trimmed) if ranking is disabled or fails.
func RankNews(news []*pb.NewsItem, hn []*pb.HNStory) ([]*pb.NewsItem, []*pb.HNStory) {
	if !config.C.RankingEnabled {
		return trimNews(news), trimHN(hn)
	}
	client := GeminiClient()
	if client == nil {
		return trimNews(news), trimHN(hn)
	}

	newsLim := config.C.NewsMaxItems
	hnLim := config.C.HNMaxStories

	var sb strings.Builder
	sb.WriteString("=== NEWS ===\n")
	for i, n := range news {
		fmt.Fprintf(&sb, "N%d: [%s] %s\n", i, n.Source, n.Headline)
	}
	sb.WriteString("\n=== HACKER NEWS ===\n")
	for i, h := range hn {
		fmt.Fprintf(&sb, "H%d: [points=%d] %s\n", i, h.Points, h.Title)
	}

	prompt := fmt.Sprintf(
		"你是一位新闻编辑。请根据以下标准对新闻和Hacker News条目进行排名：\n"+
			"1. 重要性和影响力\n2. 信息价值和知识含量\n3. 话题多样性（避免重复话题）\n\n"+
			"%s\n请从NEWS中选出最重要的 %d 条，从HACKER NEWS中选出最重要的 %d 条。\n"+
			"请严格按以下JSON格式回复，不要多余内容：\n"+
			"{\"news\": [0, 2, 1], \"hn\": [3, 1, 0]}\n"+
			"其中数组内是原始编号，按推荐顺序排列。",
		sb.String(), newsLim, hnLim)

	text := GeminiGenerate(client, prompt)
	if text == "" {
		return trimNews(news), trimHN(hn)
	}
	idx := parseIndexJSON(text)
	return reorderNews(news, idx["news"], newsLim), reorderHN(hn, idx["hn"], hnLim)
}

// RankTech ranks and trims arXiv papers + GitHub trending using Gemini.
func RankTech(arxiv []*pb.ArxivPaper, gh []*pb.GitHubRepo) ([]*pb.ArxivPaper, []*pb.GitHubRepo) {
	if !config.C.RankingEnabled {
		return trimArxiv(arxiv), trimGH(gh)
	}
	client := GeminiClient()
	if client == nil {
		return trimArxiv(arxiv), trimGH(gh)
	}

	aLim := totalArxivLimit()
	gLim := config.C.GithubTrendingMaxPerLang * len(config.C.GithubTrendingLanguages)

	var sb strings.Builder
	sb.WriteString("=== ARXIV PAPERS ===\n")
	for i, p := range arxiv {
		fmt.Fprintf(&sb, "A%d: [%s] %s\n", i, p.Category, p.Title)
	}
	sb.WriteString("\n=== GITHUB TRENDING ===\n")
	for i, g := range gh {
		fmt.Fprintf(&sb, "G%d: [%s, ★%d] %s — %s\n", i, g.Language, g.Stars, g.Name, g.Description)
	}

	prompt := fmt.Sprintf(
		"你是一位技术编辑。请根据以下标准对arXiv论文和GitHub项目进行排名：\n"+
			"1. 技术创新性和影响力\n2. 实用价值和学习价值\n3. 话题多样性\n\n"+
			"%s\n请从ARXIV PAPERS中选出最重要的 %d 篇，从GITHUB TRENDING中选出最重要的 %d 个项目。\n"+
			"请严格按以下JSON格式回复，不要多余内容：\n"+
			"{\"arxiv\": [0, 2, 1], \"github\": [3, 1, 0]}\n"+
			"其中数组内是原始编号，按推荐顺序排列。",
		sb.String(), aLim, gLim)

	text := GeminiGenerate(client, prompt)
	if text == "" {
		return trimArxiv(arxiv), trimGH(gh)
	}
	idx := parseIndexJSON(text)
	return reorderArxiv(arxiv, idx["arxiv"], aLim), reorderGH(gh, idx["github"], gLim)
}

func totalArxivLimit() int {
	n := 0
	for _, q := range config.C.ArxivQueries {
		n += q.MaxResults
	}
	return n
}

// --- index parsing & reordering ---

var codeFenceRe = regexp.MustCompile("```(?:json)?\\s*")

func parseIndexJSON(text string) map[string][]int {
	text = codeFenceRe.ReplaceAllString(text, "")
	text = strings.TrimRight(strings.TrimSpace(text), "`")

	start := strings.Index(text, "{")
	if start == -1 {
		return nil
	}
	depth, end := 0, -1
	for i := start; i < len(text); i++ {
		switch text[i] {
		case '{':
			depth++
		case '}':
			depth--
			if depth == 0 {
				end = i + 1
			}
		}
		if end > 0 {
			break
		}
	}
	if end == -1 {
		return nil
	}

	var raw map[string][]json.Number
	if err := json.Unmarshal([]byte(text[start:end]), &raw); err != nil {
		return nil
	}
	out := make(map[string][]int)
	for k, nums := range raw {
		for _, n := range nums {
			if v, err := n.Int64(); err == nil {
				out[k] = append(out[k], int(v))
			}
		}
	}
	return out
}

// Generic reorder helpers per proto type.

func reorderNews(items []*pb.NewsItem, idx []int, limit int) []*pb.NewsItem {
	if len(idx) == 0 {
		return trimNews(items)
	}
	used := map[int]bool{}
	var out []*pb.NewsItem
	for _, i := range idx {
		if i >= 0 && i < len(items) && !used[i] {
			out = append(out, items[i])
			used[i] = true
		}
		if len(out) >= limit {
			return out
		}
	}
	for i, item := range items {
		if !used[i] {
			out = append(out, item)
			if len(out) >= limit {
				break
			}
		}
	}
	return out
}

func reorderHN(items []*pb.HNStory, idx []int, limit int) []*pb.HNStory {
	if len(idx) == 0 {
		return trimHN(items)
	}
	used := map[int]bool{}
	var out []*pb.HNStory
	for _, i := range idx {
		if i >= 0 && i < len(items) && !used[i] {
			out = append(out, items[i])
			used[i] = true
		}
		if len(out) >= limit {
			return out
		}
	}
	for i, item := range items {
		if !used[i] {
			out = append(out, item)
			if len(out) >= limit {
				break
			}
		}
	}
	return out
}

func reorderArxiv(items []*pb.ArxivPaper, idx []int, limit int) []*pb.ArxivPaper {
	if len(idx) == 0 {
		return trimArxiv(items)
	}
	used := map[int]bool{}
	var out []*pb.ArxivPaper
	for _, i := range idx {
		if i >= 0 && i < len(items) && !used[i] {
			out = append(out, items[i])
			used[i] = true
		}
		if len(out) >= limit {
			return out
		}
	}
	for i, item := range items {
		if !used[i] {
			out = append(out, item)
			if len(out) >= limit {
				break
			}
		}
	}
	return out
}

func reorderGH(items []*pb.GitHubRepo, idx []int, limit int) []*pb.GitHubRepo {
	if len(idx) == 0 {
		return trimGH(items)
	}
	used := map[int]bool{}
	var out []*pb.GitHubRepo
	for _, i := range idx {
		if i >= 0 && i < len(items) && !used[i] {
			out = append(out, items[i])
			used[i] = true
		}
		if len(out) >= limit {
			return out
		}
	}
	for i, item := range items {
		if !used[i] {
			out = append(out, item)
			if len(out) >= limit {
				break
			}
		}
	}
	return out
}

func trimNews(s []*pb.NewsItem) []*pb.NewsItem {
	if l := config.C.NewsMaxItems; len(s) > l {
		return s[:l]
	}
	return s
}
func trimHN(s []*pb.HNStory) []*pb.HNStory {
	if l := config.C.HNMaxStories; len(s) > l {
		return s[:l]
	}
	return s
}
func trimArxiv(s []*pb.ArxivPaper) []*pb.ArxivPaper {
	if l := totalArxivLimit(); len(s) > l {
		return s[:l]
	}
	return s
}
func trimGH(s []*pb.GitHubRepo) []*pb.GitHubRepo {
	l := config.C.GithubTrendingMaxPerLang * len(config.C.GithubTrendingLanguages)
	if len(s) > l {
		return s[:l]
	}
	return s
}
