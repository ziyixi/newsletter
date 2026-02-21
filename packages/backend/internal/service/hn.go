package service

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// FetchHNStories fetches top Hacker News stories.
func FetchHNStories() ([]*pb.HNStory, error) {
	base := envOrDefault("HN_API_BASE", "https://hacker-news.firebaseio.com") + "/v0"
	limit := config.C.HNMaxStories * rankingMultiplier()

	client := &http.Client{Timeout: 10 * time.Second}
	resp, err := client.Get(base + "/topstories.json")
	if err != nil {
		return nil, fmt.Errorf("fetching HN top stories: %w", err)
	}
	defer resp.Body.Close()

	var ids []int
	if err := json.NewDecoder(resp.Body).Decode(&ids); err != nil {
		return nil, fmt.Errorf("decoding HN IDs: %w", err)
	}
	if len(ids) > limit {
		ids = ids[:limit]
	}

	var out []*pb.HNStory
	for _, id := range ids {
		r, err := client.Get(fmt.Sprintf("%s/item/%d.json", base, id))
		if err != nil {
			fmt.Printf("⚠️  Failed to fetch HN story %d: %v\n", id, err)
			continue
		}
		var item struct {
			Title       string `json:"title"`
			URL         string `json:"url"`
			Score       int32  `json:"score"`
			Descendants int32  `json:"descendants"`
		}
		if err := json.NewDecoder(r.Body).Decode(&item); err != nil {
			r.Body.Close()
			continue
		}
		r.Body.Close()

		storyURL := item.URL
		if storyURL == "" {
			storyURL = fmt.Sprintf("https://news.ycombinator.com/item?id=%d", id)
		}
		out = append(out, &pb.HNStory{
			Title:        item.Title,
			Url:          storyURL,
			Points:       item.Score,
			CommentCount: item.Descendants,
			HnUrl:        fmt.Sprintf("https://news.ycombinator.com/item?id=%d", id),
		})
	}

	for _, s := range out {
		s.TitleCn = TranslateToChinese(s.Title)
	}
	return out, nil
}
