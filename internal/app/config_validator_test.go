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
		Name:    "Example",
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

	duplicateSource := scraper
	duplicateSource.ID = "other"
	duplicateSource.Name = "Other"
	if err := validator.Validate(
		[]config.ScraperConfig{scraper, duplicateSource},
	); err == nil || !strings.Contains(err.Error(), "duplicate scraper source") {
		t.Fatalf("Validate() duplicate source error = %v", err)
	}

	resolvedSource := scraper
	resolvedSource.HubRoot = "https://example.com/base/"
	resolvedSource.Route = "feed.xml"
	equivalentSource := scraper
	equivalentSource.ID = "equivalent"
	equivalentSource.Name = "Equivalent"
	equivalentSource.HubRoot = "https://example.com/"
	equivalentSource.Route = "/base/feed.xml"
	if err := validator.Validate(
		[]config.ScraperConfig{resolvedSource, equivalentSource},
	); err == nil || !strings.Contains(err.Error(), "duplicate scraper source") {
		t.Fatalf("Validate() resolved duplicate error = %v", err)
	}

	distinctSource := equivalentSource
	distinctSource.ID = "distinct"
	distinctSource.Name = "Distinct"
	distinctSource.HubRoot = "https://example.com/base"
	distinctSource.Route = "feed.xml"
	if err := validator.Validate(
		[]config.ScraperConfig{resolvedSource, distinctSource},
	); err != nil {
		t.Fatalf("Validate() distinct resolved sources error = %v", err)
	}

	oversizedName := scraper
	oversizedName.Name = strings.Repeat("源", 256)
	if err := validator.Validate(
		[]config.ScraperConfig{oversizedName},
	); err == nil || !strings.Contains(err.Error(), "255 characters") {
		t.Fatalf("Validate() oversized name error = %v", err)
	}

	validID := scraper
	validID.ID = strings.Repeat("a", 255)
	if err := validator.Validate([]config.ScraperConfig{validID}); err != nil {
		t.Fatalf("Validate() valid ID error = %v", err)
	}

	oversizedID := scraper
	oversizedID.ID = strings.Repeat("a", 256)
	if err := validator.Validate(
		[]config.ScraperConfig{oversizedID},
	); err == nil || !strings.Contains(err.Error(), "255 characters") {
		t.Fatalf("Validate() oversized ID error = %v", err)
	}
}
