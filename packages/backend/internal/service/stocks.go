package service

import (
	"fmt"
	"math"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// FetchStocks returns quotes for configured stock symbols via Yahoo Finance.
func FetchStocks() ([]*pb.StockInfo, error) {
	var out []*pb.StockInfo
	for _, sym := range config.C.StockSymbols {
		q, err := FetchYahooQuote(sym)
		if err != nil {
			fmt.Printf("⚠️  Failed to fetch stock %s: %v\n", sym, err)
			continue
		}
		if q.Price == 0 || q.PrevClose == 0 {
			continue
		}
		chg := q.Price - q.PrevClose
		pct := (chg / q.PrevClose) * 100
		name := sym
		if n, ok := config.C.StockNames[sym]; ok {
			name = n
		}
		out = append(out, &pb.StockInfo{
			Symbol:        sym,
			CompanyName:   name,
			Price:         math.Round(q.Price*100) / 100,
			Change:        math.Round(chg*100) / 100,
			ChangePercent: math.Round(pct*100) / 100,
		})
	}
	return out, nil
}
