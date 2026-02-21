package service

import (
	"fmt"
	"time"

	"github.com/nathan-osman/go-sunrise"

	"newsletter-backend/internal/config"
	pb "newsletter-backend/pb"
)

// FetchAstronomy calculates sunrise/sunset for the configured location.
func FetchAstronomy() (*pb.AstronomyData, error) {
	loc, err := time.LoadLocation(config.C.Timezone)
	if err != nil {
		return emptyAstro(), fmt.Errorf("loading timezone: %w", err)
	}

	now := time.Now().In(loc)
	rise, set := sunrise.SunriseSunset(
		config.C.WeatherLat, config.C.WeatherLon,
		now.Year(), now.Month(), now.Day(),
	)
	riseLocal := rise.In(loc)
	setLocal := set.In(loc)

	return &pb.AstronomyData{
		Sunrise:    riseLocal.Format("15:04"),
		Sunset:     setLocal.Format("15:04"),
		DayLength:  fmtDuration(setLocal.Sub(riseLocal)),
		GoldenHour: setLocal.Add(-30 * time.Minute).Format("15:04"),
	}, nil
}

func fmtDuration(d time.Duration) string {
	h := int(d.Hours())
	m := int(d.Minutes()) % 60
	return fmt.Sprintf("%d时%02d分", h, m)
}

func emptyAstro() *pb.AstronomyData {
	return &pb.AstronomyData{
		Sunrise: "--:--", Sunset: "--:--",
		DayLength: "--", GoldenHour: "--:--",
	}
}
