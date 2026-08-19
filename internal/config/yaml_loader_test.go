package config

import (
	"fmt"
	"path/filepath"
	"strings"
	"testing"
)

const validConfigYAML = `
id: example-feed
name: Example Feed
enabled: true
fetcher: direct_rss
hub_root: https://example.com
route: /feed.xml
fetch_params:
  filter_time: 60
priority: 3
content_processor_configs:
  html_content:
    priority: 10
default_keywords:
  - rss
  - rss
`

func TestYamlScraperConfigLoaderLoadValidConfig(t *testing.T) {
	directory := t.TempDir()
	path := writeConfigFile(t, directory, "feed.yaml", validConfigYAML)
	config, err := NewYamlScraperConfigLoader().Load(path)
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if config.ID != "example-feed" {
		t.Fatalf("config.ID = %q", config.ID)
	}
	if config.SourcePath != path {
		t.Fatalf("config.SourcePath = %q, want %q", config.SourcePath, path)
	}
	if got := strings.Join(config.DefaultKeywords, ","); got != "rss" {
		t.Fatalf("default keywords = %q", got)
	}
	if priority := config.ContentProcessorConfigs["html_content"]["priority"]; priority != 10 {
		t.Fatalf("processor priority = %#v", priority)
	}
}

func TestYamlScraperConfigLoaderPreservesProcessorAndCategoryOrder(t *testing.T) {
	body := strings.Replace(
		validConfigYAML,
		"  html_content:\n    priority: 10",
		`  llm_tags:
    priority: 10
    custom_categories:
      zeta:
        - last
      alpha:
        - first
  html_content:
    priority: 10`,
		1,
	)
	config, err := NewYamlScraperConfigLoader().LoadBytes("ordered.yaml", []byte(body))
	if err != nil {
		t.Fatal(err)
	}
	if got := strings.Join(config.ContentProcessorOrder, ","); got != "llm_tags,html_content" {
		t.Fatalf("processor order = %q", got)
	}
	if got := strings.Join(config.ProcessorCategoryOrders["llm_tags"], ","); got != "zeta,alpha" {
		t.Fatalf("category order = %q", got)
	}
}

func TestYamlContractFixtures(t *testing.T) {
	loader := NewYamlScraperConfigLoader()
	validPath := filepath.Join("..", "..", "contracts", "yaml", "valid.yaml")
	scraper, err := loader.Load(validPath)
	if err != nil {
		t.Fatal(err)
	}
	if scraper.ID != "example-feed" ||
		scraper.Fetcher != "direct_rss" ||
		strings.Join(scraper.DefaultKeywords, ",") != "rss" {
		t.Fatalf("unexpected contract scraper: %#v", scraper)
	}
	duplicatePath := filepath.Join(
		"..",
		"..",
		"contracts",
		"yaml",
		"duplicate-key.yaml",
	)
	if _, err := loader.Load(duplicatePath); err == nil {
		t.Fatal("duplicate-key contract unexpectedly loaded")
	}
}

func TestYamlScraperConfigLoaderRejectsInvalidDocuments(t *testing.T) {
	loader := NewYamlScraperConfigLoader()
	cases := map[string]string{
		"aliases":        validConfigYAML + "defaults: &x {}\ndefault_keywords: *x\n",
		"duplicate-key":  strings.Replace(validConfigYAML, "name: Example Feed", "name: Example Feed\nname: Other", 1),
		"unknown-field":  validConfigYAML + "unknown: true\n",
		"multiple-docs":  validConfigYAML + "---\n{}\n",
		"non-string-key": strings.Replace(validConfigYAML, "  filter_time: 60", "  ? [nested, key]\n  : value", 1),
		"float-priority": strings.Replace(validConfigYAML, "priority: 3", "priority: 3.0", 1),
		"huge-priority":  strings.Replace(validConfigYAML, "priority: 3", "priority: 18446744073709551615", 1),
	}
	for name, body := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := loader.LoadBytes(name+".yaml", []byte(body)); err == nil {
				t.Fatalf("LoadBytes() unexpectedly succeeded")
			}
		})
	}
}

func TestYamlScraperConfigLoaderRejectsDeepAndLongInput(t *testing.T) {
	loader := NewYamlScraperConfigLoader()
	deep := validConfigYAML + "fetch_params:\n  nested:\n" + strings.Repeat("    level:\n", MaxConfigDepth+1) + "      value: 1\n"
	if _, err := loader.LoadBytes("deep.yaml", []byte(deep)); err == nil {
		t.Fatalf("LoadBytes() unexpectedly accepted deep input")
	}
	longString := strings.Replace(validConfigYAML, "name: Example Feed", fmt.Sprintf("name: %s", strings.Repeat("a", MaxStringLength+1)), 1)
	if _, err := loader.LoadBytes("long.yaml", []byte(longString)); err == nil {
		t.Fatalf("LoadBytes() unexpectedly accepted long string")
	}
}

func TestYamlScraperConfigLoaderValidatesSupportedFetchersProcessorsAndParams(t *testing.T) {
	loader := NewYamlScraperConfigLoader()
	cases := map[string]struct {
		body    string
		wantErr bool
	}{
		"unsupported-fetcher": {
			body:    strings.Replace(validConfigYAML, "fetcher: direct_rss", "fetcher: missing", 1),
			wantErr: true,
		},
		"unsupported-processor": {
			body:    strings.Replace(validConfigYAML, "html_content", "missing_processor", 1),
			wantErr: true,
		},
		"unsupported-direct-param": {
			body:    strings.Replace(validConfigYAML, "  filter_time: 60", "  unsupported: 1", 1),
			wantErr: false,
		},
		"rsshub-param": {
			body:    strings.Replace(strings.Replace(validConfigYAML, "fetcher: direct_rss", "fetcher: rsshub", 1), "  filter_time: 60", "  mode: fulltext", 1),
			wantErr: false,
		},
	}
	for name, tc := range cases {
		t.Run(name, func(t *testing.T) {
			_, err := loader.LoadBytes(name+".yaml", []byte(tc.body))
			if tc.wantErr && err == nil {
				t.Fatalf("LoadBytes() unexpectedly succeeded")
			}
			if !tc.wantErr && err != nil {
				t.Fatalf("LoadBytes() error = %v", err)
			}
		})
	}
}

func TestYamlScraperConfigLoaderRejectsNodeHeavyMappings(t *testing.T) {
	loader := NewYamlScraperConfigLoader()
	var builder strings.Builder
	builder.WriteString("id: example-feed\nname: Example Feed\nfetcher: rsshub\nhub_root: https://example.com\nroute: /feed.xml\nfetch_params:\n")
	for index := 0; index <= MaxConfigNodes; index++ {
		builder.WriteString(fmt.Sprintf("  key_%d: value\n", index))
	}
	if _, err := loader.LoadBytes("heavy.yaml", []byte(builder.String())); err == nil {
		t.Fatalf("LoadBytes() unexpectedly accepted node-heavy mapping")
	}
}
