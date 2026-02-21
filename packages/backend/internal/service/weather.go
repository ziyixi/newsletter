package service

import (
	"encoding/json"
	"fmt"
	"io"
	"math"
	"net/http"
	"os"
	"time"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

var wmoCodes = map[int][2]string{
	0: {"晴", "☀️"}, 1: {"大部晴朗", "🌤"}, 2: {"局部多云", "⛅"}, 3: {"多云", "☁️"},
	45: {"雾", "🌫"}, 48: {"雾凇", "🌫"},
	51: {"小毛毛雨", "🌦"}, 53: {"毛毛雨", "🌦"}, 55: {"密集毛毛雨", "🌦"},
	61: {"小雨", "🌧"}, 63: {"中雨", "🌧"}, 65: {"大雨", "🌧"},
	66: {"冻雨（小）", "🌧"}, 67: {"冻雨（大）", "🌧"},
	71: {"小雪", "🌨"}, 73: {"中雪", "🌨"}, 75: {"大雪", "🌨"}, 77: {"雪粒", "🌨"},
	80: {"小阵雨", "🌦"}, 81: {"中阵雨", "🌦"}, 82: {"大阵雨", "🌧"},
	85: {"小阵雪", "🌨"}, 86: {"大阵雪", "🌨"},
	95: {"雷暴", "⛈"}, 96: {"雷暴伴小冰雹", "⛈"}, 99: {"雷暴伴大冰雹", "⛈"},
}

var weekdayShort = []string{"周一", "周二", "周三", "周四", "周五", "周六", "周日"}

// FetchWeather fetches current weather and 3-day forecast from Open-Meteo.
func FetchWeather() (*pb.WeatherData, error) {
	base := envOrDefault("WEATHER_API_BASE", "https://api.open-meteo.com")
	u := fmt.Sprintf(
		"%s/v1/forecast?latitude=%f&longitude=%f&current=temperature_2m,weather_code,wind_speed_10m"+
			"&daily=temperature_2m_max,temperature_2m_min,weather_code&timezone=%s&forecast_days=4",
		base, config.C.WeatherLat, config.C.WeatherLon, config.C.Timezone,
	)

	resp, err := (&http.Client{Timeout: 10 * time.Second}).Get(u)
	if err != nil {
		return nil, fmt.Errorf("weather request: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("weather API %d: %s", resp.StatusCode, body)
	}

	var raw struct {
		Current struct {
			Temp        float64 `json:"temperature_2m"`
			WeatherCode int     `json:"weather_code"`
			WindSpeed   float64 `json:"wind_speed_10m"`
		} `json:"current"`
		Daily struct {
			TempMax []float64 `json:"temperature_2m_max"`
			TempMin []float64 `json:"temperature_2m_min"`
			Code    []int     `json:"weather_code"`
		} `json:"daily"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil {
		return nil, fmt.Errorf("decoding weather: %w", err)
	}

	cond, icon := wmoLookup(raw.Current.WeatherCode)
	cur := int32(math.Round(raw.Current.Temp))
	hi := int32(math.Round(raw.Daily.TempMax[0]))
	lo := int32(math.Round(raw.Daily.TempMin[0]))

	w := &pb.WeatherData{
		Location:    config.C.WeatherLocationName,
		Condition:   cond,
		Icon:        icon,
		TempCurrent: cur,
		TempHigh:    hi,
		TempLow:     lo,
		Summary: fmt.Sprintf("当前%s，气温%d°C。今日最高%d°C，最低%d°C。%s。",
			cond, cur, hi, lo, windDesc(raw.Current.WindSpeed)),
	}

	today := time.Now()
	for i := 1; i < 4; i++ {
		d := today.AddDate(0, 0, i)
		code := safeIdx(raw.Daily.Code, i)
		dc, di := wmoLookup(code)
		w.Forecasts = append(w.Forecasts, &pb.ForecastDay{
			Label:     weekdayShort[goWeekdayToZH(d.Weekday())],
			Icon:      di,
			Condition: dc,
			High:      int32(math.Round(safeFloat(raw.Daily.TempMax, i))),
			Low:       int32(math.Round(safeFloat(raw.Daily.TempMin, i))),
		})
	}
	return w, nil
}

// goWeekdayToZH converts Go's Sunday=0 weekday to Python-style Monday=0.
func goWeekdayToZH(wd time.Weekday) int { return (int(wd) + 6) % 7 }

func wmoLookup(code int) (string, string) {
	if v, ok := wmoCodes[code]; ok {
		return v[0], v[1]
	}
	return "未知", "❓"
}

func windDesc(kmh float64) string {
	switch {
	case kmh < 5:
		return "微风"
	case kmh < 20:
		return fmt.Sprintf("风速约%.0f公里/时", kmh)
	case kmh < 40:
		return fmt.Sprintf("较强风，风速%.0f公里/时", kmh)
	default:
		return fmt.Sprintf("大风，风速%.0f公里/时", kmh)
	}
}

func safeIdx(s []int, i int) int {
	if i < len(s) {
		return s[i]
	}
	return 0
}

func safeFloat(s []float64, i int) float64 {
	if i < len(s) {
		return s[i]
	}
	return 0
}

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}
