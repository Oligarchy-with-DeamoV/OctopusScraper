package fetcher

import (
	"context"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/content"
)

// Fetcher loads content from one configured source.
type Fetcher interface {
	Fetch(context.Context, map[string]any) ([]content.Content, error)
}

// Factory builds a fetcher from a scraper configuration.
type Factory interface {
	Create(name string, rawConfig map[string]any) (Fetcher, error)
}
