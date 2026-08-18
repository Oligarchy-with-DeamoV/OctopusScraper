package app

import (
	"strings"
	"testing"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/processor"
)

func TestScraperConfigValidatorChecksProcessorConstruction(t *testing.T) {
	validator := NewScraperConfigValidator(
		fetcher.NewFactory(),
		processor.NewRegistry(),
	)
	scraper := config.ScraperConfig{
		ID:      "example",
		Fetcher: "direct_rss",
		HubRoot: "https://example.com",
		Route:   "/feed.xml",
		ContentProcessorConfigs: map[string]map[string]any{
			"html_content": {"use_browser": "true"},
		},
	}
	err := validator.Validate([]config.ScraperConfig{scraper})
	if err == nil || !strings.Contains(err.Error(), "use_browser") {
		t.Fatalf("Validate() error = %v", err)
	}

	scraper.ContentProcessorConfigs["html_content"] = map[string]any{
		"use_browser": false,
	}
	if err := validator.Validate([]config.ScraperConfig{scraper}); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}

	duplicate := scraper
	duplicate.Name = "duplicate"
	if err := validator.Validate(
		[]config.ScraperConfig{scraper, duplicate},
	); err == nil || !strings.Contains(err.Error(), "duplicate scraper id") {
		t.Fatalf("Validate() duplicate error = %v", err)
	}
}
