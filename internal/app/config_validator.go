package app

import (
	"fmt"
	"sort"
	"unicode/utf8"

	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/config"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/fetcher"
	"github.com/Oligarchy-with-DeamoV/OctopusScraper/internal/processor"
)

// ScraperConfigValidator verifies runtime construction without external calls.
type ScraperConfigValidator struct {
	fetchers   fetcher.Factory
	processors processor.Factory
}

func NewScraperConfigValidator(
	fetchers fetcher.Factory,
	processors processor.Factory,
) *ScraperConfigValidator {
	return &ScraperConfigValidator{
		fetchers:   fetchers,
		processors: processors,
	}
}

func (v *ScraperConfigValidator) Validate(
	scrapers []config.ScraperConfig,
) error {
	if v == nil || v.fetchers == nil || v.processors == nil {
		return fmt.Errorf("scraper configuration validator is incomplete")
	}
	ids := make(map[string]struct{}, len(scrapers))
	names := make(map[string]struct{}, len(scrapers))
	sources := make(map[string]string, len(scrapers))
	for _, scraper := range scrapers {
		if utf8.RuneCountInString(scraper.ID) > config.MaxScraperIDLength {
			return fmt.Errorf(
				"scraper %q ID exceeds %d characters",
				scraper.ID,
				config.MaxScraperIDLength,
			)
		}
		if _, exists := ids[scraper.ID]; exists {
			return fmt.Errorf("duplicate scraper id %q", scraper.ID)
		}
		ids[scraper.ID] = struct{}{}
		if _, exists := names[scraper.Name]; exists {
			return fmt.Errorf("duplicate scraper name %q", scraper.Name)
		}
		if utf8.RuneCountInString(scraper.Name) > 255 {
			return fmt.Errorf("scraper %q name exceeds 255 characters", scraper.ID)
		}
		names[scraper.Name] = struct{}{}
		fetcherConfig := map[string]any{
			"hub_root":     scraper.HubRoot,
			"route":        scraper.Route,
			"fetch_params": scraper.FetchParams,
		}
		if _, err := v.fetchers.Create(scraper.Fetcher, fetcherConfig); err != nil {
			return fmt.Errorf("scraper %q fetcher configuration: %w", scraper.ID, err)
		}
		sourceKey, err := fetcher.CanonicalSourceIdentity(
			scraper.Fetcher,
			scraper.HubRoot,
			scraper.Route,
			scraper.FetchParams,
		)
		if err != nil {
			return fmt.Errorf("scraper %q source identity: %w", scraper.ID, err)
		}
		if existingID, exists := sources[sourceKey]; exists {
			return fmt.Errorf(
				"duplicate scraper source %q and %q",
				existingID,
				scraper.ID,
			)
		}
		sources[sourceKey] = scraper.ID
		names := make([]string, 0, len(scraper.ContentProcessorConfigs))
		for name := range scraper.ContentProcessorConfigs {
			names = append(names, name)
		}
		sort.Strings(names)
		for _, name := range names {
			if _, err := v.processors.Create(
				name,
				scraper.ContentProcessorConfigs[name],
			); err != nil {
				return fmt.Errorf(
					"scraper %q processor %q configuration: %w",
					scraper.ID,
					name,
					err,
				)
			}
		}
	}
	return nil
}
