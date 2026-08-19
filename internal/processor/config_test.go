package processor

import "testing"

func TestParseBaseLLMConfigUsesEnvironmentDefaults(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "env-key")
	t.Setenv("OPENAI_BASE_URL", "https://example.com/v1")
	t.Setenv("OPENAI_MODEL_NAME", "env-model")

	cfg, err := parseBaseLLMConfig(map[string]any{})
	if err != nil {
		t.Fatalf("parseBaseLLMConfig() error = %v", err)
	}
	if cfg.APIKey != "env-key" {
		t.Fatalf("APIKey = %q, want %q", cfg.APIKey, "env-key")
	}
	if cfg.APIBase != "https://example.com/v1" {
		t.Fatalf("APIBase = %q, want %q", cfg.APIBase, "https://example.com/v1")
	}
	if cfg.BaseURL != "https://example.com/v1" {
		t.Fatalf("BaseURL = %q, want %q", cfg.BaseURL, "https://example.com/v1")
	}
	if cfg.ModelName != "env-model" {
		t.Fatalf("ModelName = %q, want %q", cfg.ModelName, "env-model")
	}
}

func TestParseBaseLLMConfigPrefersYAMLValues(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "env-key")
	t.Setenv("OPENAI_BASE_URL", "https://example.com/v1")
	t.Setenv("OPENAI_MODEL_NAME", "env-model")

	cfg, err := parseBaseLLMConfig(map[string]any{
		"api_key":    "yaml-key",
		"api_base":   "https://yaml-base.example/v1",
		"base_url":   "https://yaml-url.example/v1",
		"model_name": "yaml-model",
	})
	if err != nil {
		t.Fatalf("parseBaseLLMConfig() error = %v", err)
	}
	if cfg.APIKey != "yaml-key" {
		t.Fatalf("APIKey = %q, want %q", cfg.APIKey, "yaml-key")
	}
	if cfg.APIBase != "https://yaml-base.example/v1" {
		t.Fatalf("APIBase = %q, want %q", cfg.APIBase, "https://yaml-base.example/v1")
	}
	if cfg.BaseURL != "https://yaml-url.example/v1" {
		t.Fatalf("BaseURL = %q, want %q", cfg.BaseURL, "https://yaml-url.example/v1")
	}
	if cfg.ModelName != "yaml-model" {
		t.Fatalf("ModelName = %q, want %q", cfg.ModelName, "yaml-model")
	}
}

func TestParseBaseLLMConfigFallsBackToBuiltins(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "")
	t.Setenv("OPENAI_BASE_URL", "")
	t.Setenv("OPENAI_MODEL_NAME", "")

	cfg, err := parseBaseLLMConfig(map[string]any{})
	if err != nil {
		t.Fatalf("parseBaseLLMConfig() error = %v", err)
	}
	if cfg.APIKey != "" {
		t.Fatalf("APIKey = %q, want empty", cfg.APIKey)
	}
	if cfg.BaseURL != defaultOpenAIBaseURL {
		t.Fatalf("BaseURL = %q, want %q", cfg.BaseURL, defaultOpenAIBaseURL)
	}
	if cfg.ModelName != defaultSummaryModel {
		t.Fatalf("ModelName = %q, want %q", cfg.ModelName, defaultSummaryModel)
	}
}

func TestParseBaseLLMConfigUsesAPIBaseWhenBaseURLIsAbsent(t *testing.T) {
	cfg, err := parseBaseLLMConfig(map[string]any{
		"api_base": "https://gateway.example/v1",
	})
	if err != nil {
		t.Fatalf("parseBaseLLMConfig() error = %v", err)
	}
	if cfg.BaseURL != "https://gateway.example/v1" {
		t.Fatalf("BaseURL = %q", cfg.BaseURL)
	}
}

func TestParseBaseLLMConfigDoesNotSendGlobalKeyToCustomEndpoint(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "global-key")
	t.Setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

	cfg, err := parseBaseLLMConfig(map[string]any{
		"base_url": "https://llm-gateway.example/v1",
	})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.APIKey != "" {
		t.Fatalf("custom endpoint inherited API key %q", cfg.APIKey)
	}

	cfg, err = parseBaseLLMConfig(map[string]any{
		"base_url": "https://llm-gateway.example/v1",
		"api_key":  "gateway-key",
	})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.APIKey != "gateway-key" {
		t.Fatalf("explicit API key = %q", cfg.APIKey)
	}
}

func TestParseBaseLLMConfigRetainsGlobalKeyForSameEndpoint(t *testing.T) {
	t.Setenv("OPENAI_API_KEY", "global-key")
	t.Setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

	cfg, err := parseBaseLLMConfig(map[string]any{
		"api_base": "https://API.OPENAI.COM/v1/",
	})
	if err != nil {
		t.Fatal(err)
	}
	if cfg.APIKey != "global-key" {
		t.Fatalf("same endpoint API key = %q", cfg.APIKey)
	}
}

func TestParseTagsConfigKeepsTagLimitsIndependent(t *testing.T) {
	cfg, err := parseTagsConfig(map[string]any{
		"max_tags":       7,
		"max_tags_count": 2,
	})
	if err != nil {
		t.Fatalf("parseTagsConfig() error = %v", err)
	}
	if cfg.MaxTags != 7 || cfg.MaxTagsCount != 2 {
		t.Fatalf(
			"tag limits = (%d, %d), want (7, 2)",
			cfg.MaxTags,
			cfg.MaxTagsCount,
		)
	}
}

func TestProcessorConfigsRejectInvalidProvidedTypes(t *testing.T) {
	tests := []struct {
		name  string
		parse func(map[string]any) error
		raw   map[string]any
	}{
		{
			name: "HTML boolean",
			parse: func(raw map[string]any) error {
				_, err := parseHTMLConfig(raw)
				return err
			},
			raw: map[string]any{"use_browser": "true"},
		},
		{
			name: "LLM integer",
			parse: func(raw map[string]any) error {
				_, err := parseBaseLLMConfig(raw)
				return err
			},
			raw: map[string]any{"max_tokens": 10.5},
		},
		{
			name: "keywords list",
			parse: func(raw map[string]any) error {
				_, err := parseKeywordsConfig(raw)
				return err
			},
			raw: map[string]any{"exclude_patterns": []any{"valid", 3}},
		},
		{
			name: "tags categories",
			parse: func(raw map[string]any) error {
				_, err := parseTagsConfig(raw)
				return err
			},
			raw: map[string]any{
				"custom_categories": map[string]any{"topic": "invalid"},
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if err := test.parse(test.raw); err == nil {
				t.Fatalf("configuration unexpectedly accepted: %#v", test.raw)
			}
		})
	}
}

func TestProcessorConfigsRejectInvalidValues(t *testing.T) {
	tests := []map[string]any{
		{"model_name": ""},
		{"temperature": 2.1},
		{"retry_times": 0},
		{"timeout": 0},
		{"timeout": int(^uint(0) >> 1)},
		{"llm_provider": "anthropic"},
		{"base_url": "file:///tmp/model"},
	}
	for _, raw := range tests {
		if _, err := parseBaseLLMConfig(raw); err == nil {
			t.Fatalf("configuration unexpectedly accepted: %#v", raw)
		}
	}
}
