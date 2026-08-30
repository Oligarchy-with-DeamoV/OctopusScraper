package content

import (
	"net/http"
	"strings"
	"time"
)

var publishedTimeLayouts = []string{
	time.RFC3339Nano,
	time.RFC3339,
	time.RFC1123Z,
	time.RFC822Z,
	time.RubyDate,
	"2006-01-02 15:04:05Z07:00",
	"2006-01-02 15:04:05 -0700",
	"2006-01-02 15:04:05",
	"2006-01-02",
}

var namedPublishedTimeLayouts = []string{
	time.RFC1123,
	time.RFC822,
	time.RFC850,
	"Mon, 02 Jan 2006 15:04:05 MST",
	"2006-01-02 15:04:05 -0700 MST",
}

var namedZoneOffsets = map[string]int{
	"UT":  0,
	"GMT": 0,
	"UTC": 0,
	"EST": -5 * 60 * 60,
	"EDT": -4 * 60 * 60,
	"CST": -6 * 60 * 60,
	"CDT": -5 * 60 * 60,
	"MST": -7 * 60 * 60,
	"MDT": -6 * 60 * 60,
	"PST": -8 * 60 * 60,
	"PDT": -7 * 60 * 60,
}

// ParsePublishedTime normalizes supported RSS and Atom publication timestamps.
func ParsePublishedTime(value string) (time.Time, bool) {
	value = strings.TrimSpace(value)
	if value == "" {
		return time.Time{}, false
	}
	for _, layout := range publishedTimeLayouts {
		if parsed, err := time.Parse(layout, value); err == nil {
			return parsed.UTC(), true
		}
	}
	for _, layout := range namedPublishedTimeLayouts {
		parsed, err := time.Parse(layout, value)
		if err != nil {
			continue
		}
		if strings.Contains(layout, "-0700 MST") {
			return parsed.UTC(), true
		}
		zone, _ := parsed.Zone()
		offset, ok := namedZoneOffsets[zone]
		if !ok {
			continue
		}
		parsed = time.Date(
			parsed.Year(),
			parsed.Month(),
			parsed.Day(),
			parsed.Hour(),
			parsed.Minute(),
			parsed.Second(),
			parsed.Nanosecond(),
			time.FixedZone(zone, offset),
		)
		return parsed.UTC(), true
	}
	if parsed, err := http.ParseTime(value); err == nil {
		zone, _ := parsed.Zone()
		if zone == "UTC" || zone == "GMT" || zone == "UT" {
			return parsed.UTC(), true
		}
		if offset, ok := namedZoneOffsets[zone]; ok {
			parsed = time.Date(
				parsed.Year(),
				parsed.Month(),
				parsed.Day(),
				parsed.Hour(),
				parsed.Minute(),
				parsed.Second(),
				parsed.Nanosecond(),
				time.FixedZone(zone, offset),
			)
			return parsed.UTC(), true
		}
	}
	return time.Time{}, false
}
