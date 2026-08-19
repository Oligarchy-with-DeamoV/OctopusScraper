package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func writeConfigFile(t *testing.T, directory, name, body string) string {
	t.Helper()
	path := filepath.Join(directory, name)
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("write config file %s: %v", path, err)
	}
	return path
}

func testScraperYAML(id, route string, enabled bool) string {
	return testScraperYAMLWithName(id, titleCase(id), route, enabled)
}

func testScraperYAMLWithName(id, name, route string, enabled bool) string {
	enabledText := "false"
	if enabled {
		enabledText = "true"
	}
	return strings.Join([]string{
		"id: " + id,
		"name: " + name,
		"enabled: " + enabledText,
		"fetcher: direct_rss",
		"hub_root: https://example.com",
		"route: " + route,
		"fetch_params:",
		"  filter_time: 60",
		"content_processor_configs: {}",
		"",
	}, "\n")
}

func titleCase(value string) string {
	if value == "" {
		return value
	}
	return strings.ToUpper(value[:1]) + value[1:]
}
