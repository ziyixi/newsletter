package service

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// FetchTodoTasks fetches recommended tasks from the todo API.
func FetchTodoTasks() ([]*pb.TodoTask, error) {
	base := envOrDefault("TODO_API_BASE", "https://daily.ziyixi.science")
	user, pass := config.C.TodoAPIUser, config.C.TodoAPIPassword
	if user == "" || pass == "" {
		fmt.Println("    ⚠️  TODO_API_USER / TODO_API_PASSWORD not set — skipping")
		return nil, nil
	}

	const maxAttempts = 2
	for attempt := 1; attempt <= maxAttempts; attempt++ {
		req, _ := http.NewRequest("GET", base+"/api/recommendation?top=5", nil)
		req.SetBasicAuth(user, pass)

		resp, err := (&http.Client{Timeout: 45 * time.Second}).Do(req)
		if err != nil {
			fmt.Printf("    ⚠️  Todo attempt %d/%d failed: %v\n", attempt, maxAttempts, err)
			if attempt < maxAttempts {
				time.Sleep(2 * time.Second)
			}
			continue
		}
		if resp.StatusCode != http.StatusOK {
			resp.Body.Close()
			fmt.Printf("    ⚠️  Todo attempt %d/%d: status %d\n", attempt, maxAttempts, resp.StatusCode)
			if attempt < maxAttempts {
				time.Sleep(2 * time.Second)
			}
			continue
		}

		var data struct {
			Tasks []struct {
				Rank   int32  `json:"rank"`
				Title  string `json:"title"`
				Reason string `json:"reason"`
			} `json:"tasks"`
		}
		err = json.NewDecoder(resp.Body).Decode(&data)
		resp.Body.Close()
		if err != nil {
			fmt.Printf("    ⚠️  Todo attempt %d/%d: decode error: %v\n", attempt, maxAttempts, err)
			continue
		}

		var out []*pb.TodoTask
		for i, t := range data.Tasks {
			rank := t.Rank
			if rank == 0 {
				rank = int32(i + 1)
			}
			out = append(out, &pb.TodoTask{Rank: rank, Title: t.Title, Reason: t.Reason})
		}
		return out, nil
	}
	return nil, nil
}
