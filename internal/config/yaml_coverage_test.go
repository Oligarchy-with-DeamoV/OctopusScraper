package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	yaml "go.yaml.in/yaml/v4"
)

func TestYamlLoaderFileAndDocumentErrors(t *testing.T) {
	loader := NewYamlScraperConfigLoader()
	if _, err := loader.Load(filepath.Join(t.TempDir(), "missing.yaml")); err == nil {
		t.Fatal("missing file unexpectedly loaded")
	}
	oversize := filepath.Join(t.TempDir(), "large.yaml")
	if err := os.WriteFile(oversize, make([]byte, MaxConfigFileBytes+1), 0o600); err != nil {
		t.Fatal(err)
	}
	if _, err := loader.Load(oversize); err == nil {
		t.Fatal("oversize file unexpectedly loaded")
	}
	directory := filepath.Join(t.TempDir(), "directory.yaml")
	if err := os.Mkdir(directory, 0o755); err != nil {
		t.Fatal(err)
	}
	if _, err := loader.Load(directory); err == nil {
		t.Fatal("directory unexpectedly loaded as YAML")
	}
	for name, body := range map[string]string{
		"empty":           "",
		"empty-doc":       "---\n",
		"malformed":       "id: [",
		"extra-malformed": validConfigYAML + "---\n[",
		"sequence":        "- one\n- two\n",
	} {
		t.Run(name, func(t *testing.T) {
			if _, err := loader.LoadBytes(name, []byte(body)); err == nil {
				t.Fatalf("LoadBytes(%q) unexpectedly succeeded", name)
			}
		})
	}
}

func TestYamlLoaderValidationTypeMatrix(t *testing.T) {
	base := validConfigYAML
	replacements := map[string]string{
		"missing id":        "id: example-feed",
		"empty id":          "id: '   '",
		"bad id":            "id: Invalid",
		"missing name":      "name: Example Feed",
		"bad enabled":       "enabled: yes",
		"bad fetcher":       "fetcher: 2",
		"unknown fetcher":   "fetcher: unknown",
		"bad root":          "hub_root: /relative",
		"ftp root":          "hub_root: ftp://example.com",
		"bad priority":      "priority: nope",
		"priority range":    "priority: 11",
		"bad params":        "fetch_params: []",
		"bad processors":    "content_processor_configs: []",
		"bad processor map": "  html_content: []",
		"bad keywords":      "default_keywords: nope",
		"keyword item":      "  - 2",
	}
	for name, replacement := range replacements {
		t.Run(name, func(t *testing.T) {
			body := base
			switch name {
			case "missing id":
				body = strings.Replace(body, "id: example-feed\n", "", 1)
			case "missing name":
				body = strings.Replace(body, "name: Example Feed\n", "", 1)
			case "bad processor map":
				body = strings.Replace(body, "    priority: 10", "    - invalid", 1)
			case "keyword item":
				body = strings.Replace(body, "  - rss\n", "  - 2\n", 1)
			default:
				field := strings.Split(replacement, ":")[0]
				if field == "content_processor_configs" {
					body = strings.Replace(body, "content_processor_configs:\n  html_content:\n    priority: 10", replacement, 1)
				} else if field == "default_keywords" {
					body = strings.Replace(body, "default_keywords:\n  - rss\n  - rss", replacement, 1)
				} else {
					body = replaceYAMLField(body, field, replacement)
				}
			}
			if _, err := NewYamlScraperConfigLoader().LoadBytes(name, []byte(body)); err == nil {
				t.Fatalf("invalid %s unexpectedly loaded", name)
			}
		})
	}
}

func replaceYAMLField(body, field, replacement string) string {
	lines := strings.Split(body, "\n")
	for index, line := range lines {
		if strings.HasPrefix(line, field+":") {
			lines[index] = replacement
			return strings.Join(lines, "\n")
		}
	}
	return body + "\n" + replacement + "\n"
}

func TestYamlLoaderDirectNodeAndConversionHelpers(t *testing.T) {
	count := 0
	if _, err := decodeDocument(&yaml.Node{Kind: yaml.DocumentNode}); err == nil {
		t.Fatal("decodeDocument accepted empty document")
	}
	if err := validateYAMLNode(&yaml.Node{Kind: yaml.DocumentNode}, 0, &count); err == nil {
		t.Fatal("empty document node accepted")
	}
	if _, err := decodeDocument(&yaml.Node{
		Kind: yaml.DocumentNode,
		Content: []*yaml.Node{{Kind: yaml.MappingNode, Content: []*yaml.Node{
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "key"},
			{Kind: 99, Value: "bad"},
		}}},
	}); err == nil {
		t.Fatal("decodeDocument accepted an undecodable mapping")
	}
	if _, err := decodeDocument(&yaml.Node{
		Kind:    yaml.DocumentNode,
		Content: []*yaml.Node{{Kind: yaml.SequenceNode}},
	}); err == nil {
		t.Fatal("decodeDocument accepted non-mapping root")
	}
	if err := validateYAMLNode(nil, 0, &count); err == nil {
		t.Fatal("nil YAML node accepted")
	}
	if err := validateYAMLNode(&yaml.Node{Kind: yaml.AliasNode}, 0, &count); err == nil {
		t.Fatal("alias node accepted")
	}
	if err := validateYAMLNode(&yaml.Node{Kind: yaml.ScalarNode, Value: strings.Repeat("x", MaxStringLength+1), Tag: "!!str"}, 0, &count); err == nil {
		t.Fatal("long scalar accepted")
	}
	if err := validateYAMLNode(&yaml.Node{Kind: yaml.MappingNode, Content: []*yaml.Node{{Kind: yaml.ScalarNode, Tag: "!!int", Value: "1"}, {Kind: yaml.ScalarNode, Tag: "!!str", Value: "x"}}}, 0, &count); err == nil {
		t.Fatal("non-string key accepted")
	}
	if err := validateYAMLNode(&yaml.Node{
		Kind: yaml.MappingNode,
		Content: []*yaml.Node{
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: strings.Repeat("x", MaxStringLength+1)},
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "x"},
		},
	}, 0, &count); err == nil {
		t.Fatal("long mapping key accepted")
	}
	if err := validateYAMLNode(&yaml.Node{
		Kind: yaml.MappingNode,
		Content: []*yaml.Node{
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "key"},
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "x"},
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "key"},
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "y"},
		},
	}, 0, &count); err == nil {
		t.Fatal("duplicate mapping key accepted")
	}
	tooMany := &yaml.Node{Kind: yaml.SequenceNode}
	for index := 0; index <= MaxConfigNodes; index++ {
		tooMany.Content = append(tooMany.Content, &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!int", Value: "1"})
	}
	count = 0
	if err := validateYAMLNode(tooMany, 0, &count); err == nil {
		t.Fatal("node-heavy sequence accepted")
	}
	if err := validateYAMLNode(&yaml.Node{Kind: 99}, 0, &count); err == nil {
		t.Fatal("unsupported node kind accepted")
	}
	deep := &yaml.Node{Kind: yaml.ScalarNode, Tag: "!!str", Value: "x"}
	for index := 0; index <= MaxConfigDepth; index++ {
		deep = &yaml.Node{Kind: yaml.SequenceNode, Content: []*yaml.Node{deep}}
	}
	count = 0
	if err := validateYAMLNode(deep, 0, &count); err == nil {
		t.Fatal("deep node accepted")
	}
	if mappingValue(nil, "x") != nil || mappingKeys(nil) != nil {
		t.Fatal("nil mapping helpers returned values")
	}
	if mappingValue(&yaml.Node{Kind: yaml.ScalarNode}, "x") != nil ||
		mappingKeys(&yaml.Node{Kind: yaml.ScalarNode}) != nil {
		t.Fatal("scalar mapping helpers returned values")
	}
	for _, value := range []any{
		int(1), int8(1), int16(1), int32(1), int64(1),
		uint(1), uint8(1), uint16(1), uint32(1), uint64(1),
	} {
		if _, err := toInt(value); err != nil {
			t.Fatalf("toInt(%T) error = %v", value, err)
		}
	}
	if _, err := toInt("not-int"); err == nil {
		t.Fatal("toInt accepted string")
	}
	maxInt := uint64(^uint(0) >> 1)
	if _, err := toInt(maxInt); err != nil {
		t.Fatalf("toInt(maxInt) error = %v", err)
	}
	if _, err := toInt(maxInt + 1); err == nil {
		t.Fatal("toInt accepted positive overflow")
	}
	if _, err := toInt(uint(maxInt + 1)); err == nil {
		t.Fatal("toInt accepted uint overflow")
	}
}

func TestYamlLoaderScalarAndProcessorDefaults(t *testing.T) {
	raw := map[string]any{
		"id": "example-feed", "name": "Example", "fetcher": "direct_rss",
		"hub_root": "https://example.com", "route": "/feed",
		"enabled": true, "fetch_params": nil,
		"content_processor_configs": nil, "default_keywords": nil,
	}
	config, err := validateScraperConfig(raw)
	if err != nil || config.Priority != 5 || config.FetchParams == nil ||
		config.ContentProcessorConfigs == nil || config.DefaultKeywords == nil {
		t.Fatalf("defaults = %#v, err=%v", config, err)
	}
	for _, value := range []any{nil, true, int(1), "   "} {
		if _, err := requiredString(map[string]any{"field": value}, "field"); err == nil {
			t.Fatalf("requiredString accepted %v", value)
		}
	}
	if _, err := boolWithDefault(map[string]any{"enabled": "yes"}, "enabled", true); err == nil {
		t.Fatal("boolWithDefault accepted string")
	}
	if _, err := mapWithDefault(map[string]any{"params": []any{}}, "params"); err == nil {
		t.Fatal("mapWithDefault accepted sequence")
	}
	if _, err := nestedStringMap(map[string]any{"processors": map[string]any{"p": []any{}}}, "processors"); err == nil {
		t.Fatal("nestedStringMap accepted sequence")
	}
	if _, err := keywordList(map[string]any{"keywords": []any{1}}, "keywords"); err == nil {
		t.Fatal("keywordList accepted non-string")
	}
	if err := validateProcessorConfigs(map[string]map[string]any{"unknown": {}}); err == nil {
		t.Fatal("unknown processor accepted")
	}
	if _, err := validateScraperConfig(map[string]any{
		"id": "id", "name": "name", "fetcher": "direct_rss",
		"hub_root": "https://example.com",
	}); err == nil {
		t.Fatal("missing route accepted")
	}
	if _, err := validateScraperConfig(map[string]any{
		"id": "id", "name": "name", "fetcher": "direct_rss",
		"hub_root": "https://example.com", "route": "/",
		"content_processor_configs": map[string]any{"p": true},
	}); err == nil {
		t.Fatal("bad processor configuration accepted")
	}
	if _, err := keywordList(map[string]any{"keywords": []any{" ", "x", "x"}}, "keywords"); err != nil {
		t.Fatal(err)
	}
	if order, categories := processorOrders(nil); order != nil || categories != nil {
		t.Fatalf("nil processor order = %v/%v", order, categories)
	}
	if order, categories := processorOrders(&yaml.Node{Kind: yaml.DocumentNode, Content: []*yaml.Node{{Kind: yaml.MappingNode}}}); order != nil || categories != nil {
		t.Fatalf("missing processor order = %v/%v", order, categories)
	}
	if order, categories := processorOrders(&yaml.Node{
		Kind: yaml.DocumentNode,
		Content: []*yaml.Node{{Kind: yaml.MappingNode, Content: []*yaml.Node{
			{Kind: yaml.ScalarNode, Tag: "!!str", Value: "content_processor_configs"},
			{Kind: yaml.MappingNode, Content: []*yaml.Node{
				{Kind: yaml.ScalarNode, Tag: "!!str", Value: "html_content"},
				{Kind: yaml.MappingNode},
			}},
		}}},
	}); len(order) != 1 || categories["html_content"] != nil {
		t.Fatalf("processor order without categories = %v/%v", order, categories)
	}
}
