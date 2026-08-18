package config

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"net/url"
	"os"
	"regexp"
	"sort"
	"strings"

	yaml "go.yaml.in/yaml/v4"
)

var (
	scraperIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9._-]*$`)
	allowedFields    = map[string]struct{}{
		"id": {}, "name": {}, "enabled": {}, "fetcher": {}, "hub_root": {},
		"route": {}, "fetch_params": {}, "priority": {},
		"content_processor_configs": {}, "default_keywords": {},
	}
	supportedFetchers = map[string]struct{}{
		"rsshub":     {},
		"direct_rss": {},
	}
	supportedProcessors = map[string]struct{}{
		"html_content": {},
		"llm_summary":  {},
		"llm_keywords": {},
		"llm_tags":     {},
	}
)

// ScraperConfigError reports one invalid YAML scraper file.
type ScraperConfigError struct {
	message string
}

func (e *ScraperConfigError) Error() string {
	return e.message
}

func newScraperConfigError(format string, args ...any) error {
	return &ScraperConfigError{message: fmt.Sprintf(format, args...)}
}

// YamlScraperConfigLoader strictly loads one scraper definition from one file.
type YamlScraperConfigLoader struct{}

func NewYamlScraperConfigLoader() *YamlScraperConfigLoader {
	return &YamlScraperConfigLoader{}
}

// Loader provides the integration-friendly strict YAML loading API.
type Loader struct {
	loader *YamlScraperConfigLoader
}

func NewLoader() *Loader {
	return &Loader{loader: NewYamlScraperConfigLoader()}
}

func (l *Loader) Load(path string) (ScraperConfig, error) {
	return l.loader.Load(path)
}

func (l *YamlScraperConfigLoader) Load(path string) (ScraperConfig, error) {
	info, err := os.Stat(path)
	if err != nil {
		return ScraperConfig{}, newScraperConfigError("stat config file: %v", err)
	}
	if info.Size() > MaxConfigFileBytes {
		return ScraperConfig{}, newScraperConfigError(
			"configuration file exceeds %d bytes", MaxConfigFileBytes,
		)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return ScraperConfig{}, newScraperConfigError("read config file: %v", err)
	}
	config, err := l.LoadBytes(path, data)
	if err != nil {
		return ScraperConfig{}, err
	}
	config.SourcePath = path
	return config, nil
}

func (l *YamlScraperConfigLoader) LoadBytes(source string, data []byte) (ScraperConfig, error) {
	root, err := parseSingleDocument(data)
	if err != nil {
		return ScraperConfig{}, err
	}
	count := 0
	if err := validateYAMLNode(root, 0, &count); err != nil {
		return ScraperConfig{}, err
	}
	raw, err := decodeDocument(root)
	if err != nil {
		return ScraperConfig{}, err
	}
	config, err := validateScraperConfig(raw)
	if err != nil {
		return ScraperConfig{}, err
	}
	config.ContentProcessorOrder, config.ProcessorCategoryOrders = processorOrders(root)
	config.SourcePath = source
	return config, nil
}

func processorOrders(document *yaml.Node) ([]string, map[string][]string) {
	if document == nil || len(document.Content) != 1 {
		return nil, nil
	}
	processors := mappingValue(document.Content[0], "content_processor_configs")
	if processors == nil || processors.Kind != yaml.MappingNode {
		return nil, nil
	}
	order := mappingKeys(processors)
	categoryOrders := make(map[string][]string)
	for index := 0; index < len(processors.Content); index += 2 {
		name := processors.Content[index].Value
		configNode := processors.Content[index+1]
		categories := mappingValue(configNode, "custom_categories")
		if categories == nil || categories.Kind != yaml.MappingNode {
			continue
		}
		categoryOrders[name] = mappingKeys(categories)
	}
	return order, categoryOrders
}

func mappingValue(mapping *yaml.Node, key string) *yaml.Node {
	if mapping == nil || mapping.Kind != yaml.MappingNode {
		return nil
	}
	for index := 0; index < len(mapping.Content); index += 2 {
		if mapping.Content[index].Value == key {
			return mapping.Content[index+1]
		}
	}
	return nil
}

func mappingKeys(mapping *yaml.Node) []string {
	if mapping == nil || mapping.Kind != yaml.MappingNode {
		return nil
	}
	keys := make([]string, 0, len(mapping.Content)/2)
	for index := 0; index < len(mapping.Content); index += 2 {
		keys = append(keys, mapping.Content[index].Value)
	}
	return keys
}

func parseSingleDocument(data []byte) (*yaml.Node, error) {
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	var document yaml.Node
	if err := decoder.Decode(&document); err != nil {
		if errors.Is(err, io.EOF) {
			return nil, newScraperConfigError("each file must contain exactly one YAML document")
		}
		return nil, newScraperConfigError("parse YAML: %v", err)
	}
	if document.Kind == 0 || len(document.Content) == 0 {
		return nil, newScraperConfigError("each file must contain exactly one YAML document")
	}
	var extra yaml.Node
	if err := decoder.Decode(&extra); err == nil {
		return nil, newScraperConfigError("each file must contain exactly one YAML document")
	} else if !errors.Is(err, io.EOF) {
		return nil, newScraperConfigError("parse YAML: %v", err)
	}
	return &document, nil
}

func validateYAMLNode(node *yaml.Node, depth int, count *int) error {
	if node == nil {
		return newScraperConfigError("YAML document must not be empty")
	}
	*count = *count + 1
	if *count > MaxConfigNodes {
		return newScraperConfigError("configuration contains too many values")
	}
	if depth > MaxConfigDepth {
		return newScraperConfigError("configuration nesting is too deep")
	}
	if node.Kind == yaml.AliasNode {
		return newScraperConfigError("YAML aliases are not supported")
	}

	switch node.Kind {
	case yaml.DocumentNode:
		if len(node.Content) != 1 {
			return newScraperConfigError("each file must contain exactly one YAML document")
		}
		return validateYAMLNode(node.Content[0], depth, count)
	case yaml.MappingNode:
		seen := make(map[string]struct{}, len(node.Content)/2)
		for index := 0; index < len(node.Content); index += 2 {
			keyNode := node.Content[index]
			valueNode := node.Content[index+1]
			*count = *count + 1
			if *count > MaxConfigNodes {
				return newScraperConfigError("configuration contains too many values")
			}
			if keyNode.Kind != yaml.ScalarNode || keyNode.ShortTag() != "!!str" {
				return newScraperConfigError("YAML mapping keys must be strings")
			}
			if len(keyNode.Value) > MaxStringLength {
				return newScraperConfigError("configuration string is too long")
			}
			if _, exists := seen[keyNode.Value]; exists {
				return newScraperConfigError("duplicate YAML key: %s", keyNode.Value)
			}
			seen[keyNode.Value] = struct{}{}
			if err := validateYAMLNode(valueNode, depth+1, count); err != nil {
				return err
			}
		}
		return nil
	case yaml.SequenceNode:
		for _, child := range node.Content {
			if err := validateYAMLNode(child, depth+1, count); err != nil {
				return err
			}
		}
		return nil
	case yaml.ScalarNode:
		if node.ShortTag() == "!!str" && len(node.Value) > MaxStringLength {
			return newScraperConfigError("configuration string is too long")
		}
		return nil
	default:
		return newScraperConfigError("unsupported YAML node kind: %d", node.Kind)
	}
}

func decodeDocument(document *yaml.Node) (map[string]any, error) {
	if len(document.Content) != 1 {
		return nil, newScraperConfigError("each file must contain exactly one YAML document")
	}
	root := document.Content[0]
	if root.Kind != yaml.MappingNode {
		return nil, newScraperConfigError("the YAML document must be a mapping")
	}
	var raw map[string]any
	if err := root.Decode(&raw); err != nil {
		return nil, newScraperConfigError("decode YAML mapping: %v", err)
	}
	return raw, nil
}

func validateScraperConfig(raw map[string]any) (ScraperConfig, error) {
	unknown := make([]string, 0)
	for field := range raw {
		if _, ok := allowedFields[field]; !ok {
			unknown = append(unknown, field)
		}
	}
	if len(unknown) > 0 {
		sort.Strings(unknown)
		return ScraperConfig{}, newScraperConfigError("unknown fields: %s", strings.Join(unknown, ", "))
	}

	scraperID, err := requiredString(raw, "id")
	if err != nil {
		return ScraperConfig{}, err
	}
	if !scraperIDPattern.MatchString(scraperID) {
		return ScraperConfig{}, newScraperConfigError("id must match ^[a-z0-9][a-z0-9._-]*$")
	}
	name, err := requiredString(raw, "name")
	if err != nil {
		return ScraperConfig{}, err
	}
	enabled, err := boolWithDefault(raw, "enabled", true)
	if err != nil {
		return ScraperConfig{}, err
	}
	fetcherName, err := requiredString(raw, "fetcher")
	if err != nil {
		return ScraperConfig{}, err
	}
	if _, ok := supportedFetchers[fetcherName]; !ok {
		return ScraperConfig{}, newScraperConfigError(
			"unknown fetcher %q. available: %v", fetcherName, supportedFetcherNames(),
		)
	}
	hubRoot, err := requiredString(raw, "hub_root")
	if err != nil {
		return ScraperConfig{}, err
	}
	parsedRoot, err := url.Parse(hubRoot)
	if err != nil || parsedRoot.Scheme == "" || parsedRoot.Host == "" {
		return ScraperConfig{}, newScraperConfigError("hub_root must be an absolute HTTP(S) URL")
	}
	if parsedRoot.Scheme != "http" && parsedRoot.Scheme != "https" {
		return ScraperConfig{}, newScraperConfigError("hub_root must be an absolute HTTP(S) URL")
	}
	route, err := requiredString(raw, "route")
	if err != nil {
		return ScraperConfig{}, err
	}
	priority, err := intWithDefault(raw, "priority", 5)
	if err != nil {
		return ScraperConfig{}, err
	}
	if priority < 1 || priority > 10 {
		return ScraperConfig{}, newScraperConfigError("priority must be between 1 and 10")
	}
	fetchParams, err := mapWithDefault(raw, "fetch_params")
	if err != nil {
		return ScraperConfig{}, err
	}
	processorConfigs, err := nestedStringMap(raw, "content_processor_configs")
	if err != nil {
		return ScraperConfig{}, err
	}
	if err := validateProcessorConfigs(processorConfigs); err != nil {
		return ScraperConfig{}, err
	}
	keywords, err := keywordList(raw, "default_keywords")
	if err != nil {
		return ScraperConfig{}, err
	}

	return ScraperConfig{
		ID:                      scraperID,
		Name:                    name,
		Enabled:                 enabled,
		Fetcher:                 fetcherName,
		HubRoot:                 hubRoot,
		Route:                   route,
		FetchParams:             fetchParams,
		Priority:                priority,
		ContentProcessorConfigs: processorConfigs,
		DefaultKeywords:         keywords,
	}, nil
}

func requiredString(raw map[string]any, field string) (string, error) {
	value, ok := raw[field]
	if !ok {
		return "", newScraperConfigError("%s must be a non-empty string", field)
	}
	stringValue, ok := value.(string)
	if !ok || strings.TrimSpace(stringValue) == "" {
		return "", newScraperConfigError("%s must be a non-empty string", field)
	}
	return strings.TrimSpace(stringValue), nil
}

func boolWithDefault(raw map[string]any, field string, fallback bool) (bool, error) {
	value, ok := raw[field]
	if !ok {
		return fallback, nil
	}
	boolValue, ok := value.(bool)
	if !ok {
		return false, newScraperConfigError("%s must be a boolean", field)
	}
	return boolValue, nil
}

func intWithDefault(raw map[string]any, field string, fallback int) (int, error) {
	value, ok := raw[field]
	if !ok {
		return fallback, nil
	}
	intValue, err := toInt(value)
	if err != nil {
		return 0, newScraperConfigError("%s must be an integer", field)
	}
	return intValue, nil
}

func mapWithDefault(raw map[string]any, field string) (map[string]any, error) {
	value, ok := raw[field]
	if !ok || value == nil {
		return map[string]any{}, nil
	}
	mapped, ok := value.(map[string]any)
	if !ok {
		return nil, newScraperConfigError("%s must be a mapping", field)
	}
	return cloneAnyMap(mapped), nil
}

func nestedStringMap(raw map[string]any, field string) (map[string]map[string]any, error) {
	value, ok := raw[field]
	if !ok || value == nil {
		return map[string]map[string]any{}, nil
	}
	mapped, ok := value.(map[string]any)
	if !ok {
		return nil, newScraperConfigError("%s must be a mapping", field)
	}
	result := make(map[string]map[string]any, len(mapped))
	for name, processorValue := range mapped {
		processorMap, ok := processorValue.(map[string]any)
		if !ok {
			return nil, newScraperConfigError("processor %q configuration must be a mapping", name)
		}
		result[name] = cloneAnyMap(processorMap)
	}
	return result, nil
}

func keywordList(raw map[string]any, field string) ([]string, error) {
	value, ok := raw[field]
	if !ok || value == nil {
		return []string{}, nil
	}
	items, ok := value.([]any)
	if !ok {
		return nil, newScraperConfigError("%s must be a list of strings", field)
	}
	seen := make(map[string]struct{}, len(items))
	keywords := make([]string, 0, len(items))
	for _, item := range items {
		keyword, ok := item.(string)
		if !ok {
			return nil, newScraperConfigError("%s must be a list of strings", field)
		}
		keyword = strings.TrimSpace(keyword)
		if keyword == "" {
			continue
		}
		if _, exists := seen[keyword]; exists {
			continue
		}
		seen[keyword] = struct{}{}
		keywords = append(keywords, keyword)
	}
	return keywords, nil
}

func validateProcessorConfigs(configs map[string]map[string]any) error {
	for name := range configs {
		if _, ok := supportedProcessors[name]; !ok {
			return newScraperConfigError(
				"unknown processor %q. available: %v", name, supportedProcessorNames(),
			)
		}
	}
	return nil
}

func toInt(value any) (int, error) {
	maxInt := uint64(^uint(0) >> 1)
	minInt := -int64(maxInt) - 1
	switch typed := value.(type) {
	case int:
		return typed, nil
	case int8:
		return int(typed), nil
	case int16:
		return int(typed), nil
	case int32:
		return int(typed), nil
	case int64:
		if typed < minInt || (typed >= 0 && uint64(typed) > maxInt) {
			return 0, fmt.Errorf("integer is out of range")
		}
		return int(typed), nil
	case uint:
		if uint64(typed) > maxInt {
			return 0, fmt.Errorf("integer is out of range")
		}
		return int(typed), nil
	case uint8:
		return int(typed), nil
	case uint16:
		return int(typed), nil
	case uint32:
		return int(typed), nil
	case uint64:
		if typed > maxInt {
			return 0, fmt.Errorf("integer is out of range")
		}
		return int(typed), nil
	default:
		return 0, fmt.Errorf("not an integer")
	}
}

func cloneAnyMap(input map[string]any) map[string]any {
	if len(input) == 0 {
		return map[string]any{}
	}
	result := make(map[string]any, len(input))
	for key, value := range input {
		result[key] = cloneAnyValue(value)
	}
	return result
}

func cloneAnyValue(value any) any {
	switch typed := value.(type) {
	case map[string]any:
		return cloneAnyMap(typed)
	case []any:
		copied := make([]any, len(typed))
		for index := range typed {
			copied[index] = cloneAnyValue(typed[index])
		}
		return copied
	default:
		return typed
	}
}

func supportedFetcherNames() []string {
	return sortedKeys(supportedFetchers)
}

func supportedProcessorNames() []string {
	return sortedKeys(supportedProcessors)
}

func sortedKeys[T any](values map[string]T) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
