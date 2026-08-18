package main

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestParseServeOptionsUsesBootstrapDefaultsWhenFlagsAreAbsent(t *testing.T) {
	options, err := parseServeOptions(nil)
	if err != nil {
		t.Fatal(err)
	}
	if options.Host != "" || options.Port != 0 || options.Debug ||
		options.LogLevel != "" || options.LogFormat != "" ||
		options.ScraperConfigDir != "" {
		t.Fatalf("unexpected options: %#v", options)
	}
}

func TestParseServeOptionsAcceptsOverrides(t *testing.T) {
	options, err := parseServeOptions([]string{
		"--host", "127.0.0.1",
		"--port", "9000",
		"--debug",
		"--log-level", "DEBUG",
		"--log-format", "json",
		"--scraper-config-dir", "/tmp/scrapers",
	})
	if err != nil {
		t.Fatal(err)
	}
	if options.Host != "127.0.0.1" ||
		options.Port != 9000 ||
		!options.Debug ||
		options.LogLevel != "DEBUG" ||
		options.LogFormat != "json" ||
		options.ScraperConfigDir != "/tmp/scrapers" {
		t.Fatalf("unexpected options: %#v", options)
	}
}

func TestParseServeOptionsRejectsInvalidValues(t *testing.T) {
	tests := [][]string{
		{"--port", "-1"},
		{"--port", "0"},
		{"--port", "65536"},
		{"--log-format", "xml"},
		{"--unknown"},
		{"unexpected"},
	}
	for _, arguments := range tests {
		if _, err := parseServeOptions(arguments); err == nil {
			t.Fatalf("parseServeOptions(%q) succeeded", arguments)
		}
	}
}

func TestRunHealthcheck(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		if request.URL.Path == "/healthy" {
			writer.WriteHeader(http.StatusNoContent)
			return
		}
		http.Error(writer, "unhealthy", http.StatusServiceUnavailable)
	}))
	defer server.Close()

	if err := runHealthcheck([]string{
		"--url", server.URL + "/healthy",
		"--timeout", time.Second.String(),
	}); err != nil {
		t.Fatal(err)
	}
	if err := runHealthcheck([]string{
		"--url", server.URL + "/unhealthy",
	}); err == nil {
		t.Fatal("expected unhealthy response to fail")
	}
	if err := runHealthcheck([]string{"--timeout", "invalid"}); err == nil {
		t.Fatal("expected invalid timeout to fail")
	}
	if err := runHealthcheck([]string{"--timeout", "0"}); err == nil {
		t.Fatal("expected zero timeout to fail")
	}
	if err := runHealthcheck([]string{"unexpected"}); err == nil {
		t.Fatal("expected unexpected argument to fail")
	}
	if err := runHealthcheck([]string{
		"--url", "http://127.0.0.1:1",
		"--timeout", "10ms",
	}); err == nil {
		t.Fatal("expected connection failure")
	}
}

func TestRunHealthcheckUsesServicePort(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		_ *http.Request,
	) {
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer server.Close()
	t.Setenv("SERVICE_PORT", server.URL[len("http://127.0.0.1:"):])
	if err := runHealthcheck(nil); err != nil {
		t.Fatal(err)
	}
}

func TestUsageTextCoversCommands(t *testing.T) {
	var output bytes.Buffer
	writeRootUsage(&output)
	writeServeUsage(&output)
	writeHealthcheckUsage(&output)
	for _, expected := range []string{
		"octopus_service [serve]",
		"octopus_service healthcheck",
		"--scraper-config-dir",
		"--timeout duration",
	} {
		if !bytes.Contains(output.Bytes(), []byte(expected)) {
			t.Fatalf("usage output missing %q:\n%s", expected, output.String())
		}
	}
	if !containsHelpFlag([]string{"--help"}) ||
		!containsHelpFlag([]string{"-h"}) ||
		containsHelpFlag([]string{"serve"}) {
		t.Fatal("containsHelpFlag returned an unexpected result")
	}
}
