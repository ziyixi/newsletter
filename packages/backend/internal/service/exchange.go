package service

import (
	"fmt"
	"math"
	"strings"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// FetchExchangeRates returns exchange rates for configured currency pairs.
func FetchExchangeRates() ([]*pb.ExchangeRate, error) {
	var out []*pb.ExchangeRate
	for _, pair := range config.C.ExchangeRatePairs {
		ticker := strings.ReplaceAll(pair, "/", "") + "=X"
		q, err := FetchYahooQuote(ticker)
		if err != nil {
			fmt.Printf("⚠️  Failed to fetch rate for %s: %v\n", pair, err)
			continue
		}
		if q.Price == 0 {
			continue
		}
		chg, pct := 0.0, 0.0
		if q.PrevClose != 0 {
			chg = q.Price - q.PrevClose
			pct = (chg / q.PrevClose) * 100
		}
		name := pair
		if n, ok := config.C.ExchangeRateNames[pair]; ok {
			name = n
		}
		out = append(out, &pb.ExchangeRate{
			Pair:          pair,
			Rate:          math.Round(q.Price*10000) / 10000,
			Change:        math.Round(chg*10000) / 10000,
			ChangePercent: math.Round(pct*100) / 100,
			DisplayName:   name,
		})
	}
	return out, nil
}
