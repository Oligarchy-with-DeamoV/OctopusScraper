package config

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"slices"
	"sort"
	"strings"
	"sync"
	"time"
)

type configLoader interface {
	Load(path string) (ScraperConfig, error)
}

// ChangeCallback validates one candidate runtime scraper snapshot.
type ChangeCallback func(context.Context, []ScraperConfig) error

// ConfigManager loads and hot-reloads directory-backed scraper definitions.
type ConfigManager struct {
	settings FileSettings
	loader   configLoader
	logger   *slog.Logger

	mu                 sync.RWMutex
	acceptedByPath     map[string]ScraperConfig
	fileHashes         map[string]string
	currentVersion     *Version
	lastCheck          time.Time
	healthy            bool
	errorMessage       string
	fileErrors         map[string]string
	lastDiff           *Diff
	onConfigChanged    ChangeCallback
	onHealthChange     func(bool)
	onRefreshResult    func(bool)
	pendingFingerprint string
	pendingSince       time.Time
	appliedFingerprint string
	now                func() time.Time
}

func NewConfigManager(settings FileSettings) *ConfigManager {
	return NewManager(settings, nil)
}

func NewManager(settings FileSettings, logger *slog.Logger) *ConfigManager {
	return &ConfigManager{
		settings:       settings,
		loader:         NewYamlScraperConfigLoader(),
		logger:         logger,
		acceptedByPath: make(map[string]ScraperConfig),
		fileHashes:     make(map[string]string),
		fileErrors:     make(map[string]string),
		healthy:        true,
		now:            time.Now,
	}
}

func (m *ConfigManager) SetOnConfigChanged(callback ChangeCallback) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.onConfigChanged = callback
}

func (m *ConfigManager) SetHealthObserver(observer func(bool)) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.onHealthChange = observer
}

func (m *ConfigManager) SetRefreshObserver(observer func(bool)) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.onRefreshResult = observer
}

func (m *ConfigManager) LoadInitialConfig(ctx context.Context) ([]ScraperConfig, error) {
	_, err := m.refresh(ctx, true, false)
	return m.GetCurrentScrapers(), err
}

func (m *ConfigManager) LoadInitial(ctx context.Context) ([]ScraperConfig, error) {
	return m.LoadInitialConfig(ctx)
}

func (m *ConfigManager) ReloadConfigIfChanged(ctx context.Context) (bool, error) {
	return m.refresh(ctx, true, true)
}

func (m *ConfigManager) Reload(ctx context.Context) (bool, error) {
	return m.ReloadConfigIfChanged(ctx)
}

func (m *ConfigManager) PollOnce(ctx context.Context) (bool, error) {
	return m.refresh(ctx, false, true)
}

func (m *ConfigManager) Watch(ctx context.Context) error {
	interval := m.settings.PollInterval
	if interval <= 0 {
		interval = time.Second
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
			_, _ = m.PollOnce(ctx)
		}
	}
}

func (m *ConfigManager) Start(
	ctx context.Context,
	callback func([]ScraperConfig) error,
) error {
	if callback != nil {
		m.SetOnConfigChanged(func(
			_ context.Context,
			scrapers []ScraperConfig,
		) error {
			return callback(scrapers)
		})
	}
	if m.logger != nil {
		m.logger.Info(
			"starting scraper config watcher",
			"directory", m.settings.Directory,
			"poll_interval", m.settings.PollInterval,
			"debounce", m.settings.Debounce,
		)
	}
	return m.Watch(ctx)
}

func (m *ConfigManager) GetCurrentScrapers() []ScraperConfig {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return enabledScrapers(m.acceptedByPath)
}

func (m *ConfigManager) CurrentScrapers() []ScraperConfig {
	return m.GetCurrentScrapers()
}

func (m *ConfigManager) GetAllScrapers() []ScraperConfig {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return sortedScrapers(m.acceptedByPath)
}

func (m *ConfigManager) AllScrapers() []ScraperConfig {
	return m.GetAllScrapers()
}

func (m *ConfigManager) GetFileErrors() map[string]string {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return cloneStringMap(m.fileErrors)
}

func (m *ConfigManager) FileErrors() map[string]string {
	return m.GetFileErrors()
}

func (m *ConfigManager) GetCurrentVersion() *Version {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return copyVersion(m.currentVersion)
}

func (m *ConfigManager) GetLastDiff() *Diff {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return copyDiff(m.lastDiff)
}

func (m *ConfigManager) GetStatus() Status {
	m.mu.RLock()
	defer m.mu.RUnlock()
	lastCheck := m.lastCheck
	if lastCheck.IsZero() {
		lastCheck = m.now()
	}
	return Status{
		Version:      copyVersion(m.currentVersion),
		Scrapers:     sortedScrapers(m.acceptedByPath),
		LastCheck:    lastCheck,
		NextCheck:    lastCheck.Add(m.settings.PollInterval),
		Healthy:      m.healthy,
		ErrorMessage: m.errorMessage,
		FileErrors:   cloneStringMap(m.fileErrors),
	}
}

func (m *ConfigManager) Status() Status {
	return m.GetStatus()
}

func (m *ConfigManager) ValidateScrapersConfig(scrapers []ScraperConfig) []string {
	errors := make([]string, 0)
	ids := make(map[string]struct{}, len(scrapers))
	names := make(map[string]struct{}, len(scrapers))
	for _, scraper := range scrapers {
		if _, exists := ids[scraper.ID]; exists {
			errors = append(errors, fmt.Sprintf("Duplicate scraper id: %s", scraper.ID))
		}
		ids[scraper.ID] = struct{}{}
		if _, exists := names[scraper.Name]; exists {
			errors = append(errors, fmt.Sprintf("Duplicate scraper name: %s", scraper.Name))
		}
		names[scraper.Name] = struct{}{}
	}
	return errors
}

func (m *ConfigManager) refresh(ctx context.Context, force bool, invokeCallback bool) (bool, error) {
	m.mu.Lock()
	defer m.mu.Unlock()

	fingerprint, fileHashes, err := m.scanDirectory()
	if err != nil {
		m.healthy = false
		m.errorMessage = err.Error()
		m.lastCheck = m.now()
		if m.logger != nil {
			m.logger.Error("scan config directory failed", "error", err)
		}
		m.recordHealth(false)
		m.recordRefresh(false)
		return false, err
	}
	now := m.now()
	if !force && fingerprint != m.appliedFingerprint {
		if fingerprint != m.pendingFingerprint {
			m.pendingFingerprint = fingerprint
			m.pendingSince = now
			return false, nil
		}
		if m.settings.Debounce > 0 && now.Sub(m.pendingSince) < m.settings.Debounce {
			return false, nil
		}
	}
	if fingerprint == m.appliedFingerprint {
		m.lastCheck = now
		m.healthy = true
		m.errorMessage = formatErrors(m.fileErrors)
		m.recordHealth(true)
		return false, nil
	}

	previousAccepted := cloneScraperMap(m.acceptedByPath)
	previousHashes := cloneStringMap(m.fileHashes)
	previousErrors := cloneStringMap(m.fileErrors)
	previousVersion := copyVersion(m.currentVersion)
	previousDiff := copyDiff(m.lastDiff)
	previousLastCheck := m.lastCheck
	previousApplied := m.appliedFingerprint
	previousPending := m.pendingFingerprint
	previousPendingSince := m.pendingSince

	candidate, errors := m.buildCandidate(fileHashes)
	candidateScrapers := sortedScrapers(candidate)
	previousScrapers := sortedScrapers(previousAccepted)
	newHash, err := configHash(candidateScrapers)
	if err != nil {
		m.healthy = false
		m.errorMessage = err.Error()
		m.lastCheck = now
		m.recordHealth(false)
		m.recordRefresh(false)
		return false, err
	}
	oldHash, err := configHash(previousScrapers)
	if err != nil {
		m.healthy = false
		m.errorMessage = err.Error()
		m.lastCheck = now
		m.recordHealth(false)
		m.recordRefresh(false)
		return false, err
	}
	if newHash == oldHash {
		m.acceptedByPath = candidate
		m.fileErrors = errors
		m.fileHashes = fileHashes
		m.lastCheck = now
		m.pendingFingerprint = ""
		m.pendingSince = time.Time{}
		m.appliedFingerprint = fingerprint
		m.healthy = true
		m.errorMessage = formatErrors(errors)
		m.recordHealth(true)
		m.recordRefresh(true)
		return false, nil
	}

	diff := computeScrapersDiff(previousScrapers, candidateScrapers)
	version := createVersion(candidateScrapers, now)
	version.ChangeSummary = createChangeSummary(diff)

	m.acceptedByPath = candidate
	m.fileHashes = fileHashes
	m.fileErrors = errors
	m.lastCheck = now
	m.currentVersion = &version
	m.lastDiff = &diff

	if invokeCallback && m.onConfigChanged != nil {
		if callbackErr := m.onConfigChanged(
			ctx,
			enabledScrapers(m.acceptedByPath),
		); callbackErr != nil {
			m.acceptedByPath = previousAccepted
			m.fileHashes = previousHashes
			m.fileErrors = previousErrors
			m.currentVersion = previousVersion
			m.lastDiff = previousDiff
			m.lastCheck = previousLastCheck
			m.appliedFingerprint = previousApplied
			m.pendingFingerprint = previousPending
			m.pendingSince = previousPendingSince
			m.healthy = false
			m.errorMessage = callbackErr.Error()
			if m.logger != nil {
				m.logger.Error("config callback rejected update", "error", callbackErr)
			}
			m.recordHealth(false)
			m.recordRefresh(false)
			return false, callbackErr
		}
	}

	m.pendingFingerprint = ""
	m.pendingSince = time.Time{}
	m.appliedFingerprint = fingerprint
	m.healthy = true
	m.errorMessage = formatErrors(errors)
	if m.logger != nil {
		m.logger.Info(
			"applied scraper config",
			"version_id", version.ID,
			"scrapers", len(candidateScrapers),
			"file_errors", len(errors),
		)
	}
	m.recordHealth(true)
	m.recordRefresh(true)
	return true, nil
}

func (m *ConfigManager) recordHealth(healthy bool) {
	if m.onHealthChange != nil {
		m.onHealthChange(healthy)
	}
}

func (m *ConfigManager) recordRefresh(success bool) {
	if m.onRefreshResult != nil {
		m.onRefreshResult(success)
	}
}

func (m *ConfigManager) scanDirectory() (string, map[string]string, error) {
	entries, err := os.ReadDir(m.settings.Directory)
	if err != nil {
		return "", nil, fmt.Errorf("scan config directory: %w", err)
	}
	sort.Slice(entries, func(i, j int) bool {
		return entries[i].Name() < entries[j].Name()
	})
	fileHashes := make(map[string]string)
	fingerprintData := make([][2]string, 0, len(entries))
	for _, entry := range entries {
		name := entry.Name()
		if strings.HasPrefix(name, ".") || entry.IsDir() {
			continue
		}
		ext := strings.ToLower(filepath.Ext(name))
		if ext != ".yml" && ext != ".yaml" {
			continue
		}
		fullPath := filepath.Join(m.settings.Directory, name)
		info, statErr := os.Lstat(fullPath)
		if statErr != nil {
			return "", nil, fmt.Errorf("stat config file %s: %w", fullPath, statErr)
		}
		if info.Mode()&os.ModeSymlink != 0 {
			continue
		}
		var digest string
		if info.Size() > MaxConfigFileBytes {
			digest = fmt.Sprintf("oversize:%d", info.Size())
		} else {
			data, readErr := os.ReadFile(fullPath)
			if readErr != nil {
				return "", nil, fmt.Errorf("read config file %s: %w", fullPath, readErr)
			}
			hash := sha256.Sum256(data)
			digest = hex.EncodeToString(hash[:])
		}
		fileHashes[fullPath] = digest
		fingerprintData = append(fingerprintData, [2]string{name, digest})
	}
	payload, err := json.Marshal(fingerprintData)
	if err != nil {
		return "", nil, fmt.Errorf("marshal config fingerprint: %w", err)
	}
	hash := sha256.Sum256(payload)
	return hex.EncodeToString(hash[:]), fileHashes, nil
}

func (m *ConfigManager) buildCandidate(fileHashes map[string]string) (map[string]ScraperConfig, map[string]string) {
	candidate := make(map[string]ScraperConfig, len(fileHashes))
	errors := make(map[string]string)
	changedPaths := make(map[string]struct{})
	for path, digest := range fileHashes {
		if previous, ok := m.fileHashes[path]; !ok || previous != digest {
			changedPaths[path] = struct{}{}
		}
	}
	for path, digest := range fileHashes {
		if _, changed := changedPaths[path]; !changed {
			if accepted, ok := m.acceptedByPath[path]; ok {
				candidate[path] = accepted
				continue
			}
		}
		if strings.HasPrefix(digest, "oversize:") {
			errors[path] = fmt.Sprintf("configuration file exceeds %d bytes", MaxConfigFileBytes)
			if m.logger != nil {
				m.logger.Error(
					"scraper configuration file too large",
					"path",
					path,
					"max_size_bytes",
					MaxConfigFileBytes,
				)
			}
			if accepted, ok := m.acceptedByPath[path]; ok {
				candidate[path] = accepted
			}
			continue
		}
		loaded, err := m.loader.Load(path)
		if err != nil {
			errors[path] = err.Error()
			if m.logger != nil {
				m.logger.Error(
					"invalid scraper configuration file",
					"path",
					path,
					"error",
					err,
				)
			}
			if accepted, ok := m.acceptedByPath[path]; ok {
				candidate[path] = accepted
			}
			continue
		}
		candidate[path] = loaded
	}
	m.resolveDuplicateConflicts(candidate, changedPaths, errors)
	return candidate, errors
}

func (m *ConfigManager) resolveDuplicateConflicts(
	candidate map[string]ScraperConfig,
	changedPaths map[string]struct{},
	errors map[string]string,
) {
	maxPasses := len(candidate)*2 + 2
	for pass := 0; pass < maxPasses; pass++ {
		before := candidateIdentity(candidate)
		m.resolveDuplicates(candidate, changedPaths, errors, "id")
		m.resolveDuplicates(candidate, changedPaths, errors, "name")
		if candidateIdentity(candidate) == before {
			return
		}
	}
}

func (m *ConfigManager) resolveDuplicates(candidate map[string]ScraperConfig, changedPaths map[string]struct{}, errors map[string]string, field string) {
	grouped := make(map[string][]string)
	for path, scraper := range candidate {
		value := scraper.ID
		if field == "name" {
			value = scraper.Name
		}
		grouped[value] = append(grouped[value], path)
	}
	for value, paths := range grouped {
		if len(paths) < 2 {
			continue
		}
		sort.Strings(paths)
		if m.logger != nil {
			m.logger.Error(
				"duplicate scraper configuration",
				"field",
				field,
				"value",
				value,
				"paths",
				paths,
			)
		}
		owner := ""
		priorOwners := make([]string, 0, 1)
		for _, path := range paths {
			accepted, ok := m.acceptedByPath[path]
			if !ok {
				continue
			}
			acceptedValue := accepted.ID
			if field == "name" {
				acceptedValue = accepted.Name
			}
			if acceptedValue == value {
				priorOwners = append(priorOwners, path)
			}
		}
		if len(priorOwners) == 1 {
			owner = priorOwners[0]
		}
		for _, path := range paths {
			if path == owner {
				continue
			}
			errors[path] = fmt.Sprintf("Duplicate scraper %s: %s", field, value)
			if _, changed := changedPaths[path]; changed {
				if accepted, ok := m.acceptedByPath[path]; ok {
					candidate[path] = accepted
					continue
				}
			}
			delete(candidate, path)
		}
	}
}

func candidateIdentity(candidate map[string]ScraperConfig) string {
	type identity struct {
		Path string `json:"path"`
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	paths := make([]string, 0, len(candidate))
	for path := range candidate {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	values := make([]identity, 0, len(paths))
	for _, path := range paths {
		scraper := candidate[path]
		values = append(values, identity{
			Path: path,
			ID:   scraper.ID,
			Name: scraper.Name,
		})
	}
	encoded, _ := json.Marshal(values)
	return string(encoded)
}

func cloneStringMap(input map[string]string) map[string]string {
	if len(input) == 0 {
		return map[string]string{}
	}
	result := make(map[string]string, len(input))
	for key, value := range input {
		result[key] = value
	}
	return result
}

func cloneScraperMap(input map[string]ScraperConfig) map[string]ScraperConfig {
	if len(input) == 0 {
		return map[string]ScraperConfig{}
	}
	result := make(map[string]ScraperConfig, len(input))
	for key, value := range input {
		result[key] = cloneScraper(value)
	}
	return result
}

func cloneScraper(value ScraperConfig) ScraperConfig {
	value.FetchParams = cloneAnyMap(value.FetchParams)
	value.ContentProcessorConfigs = cloneNestedMap(value.ContentProcessorConfigs)
	value.ContentProcessorOrder = append(
		[]string(nil),
		value.ContentProcessorOrder...,
	)
	value.ProcessorCategoryOrders = cloneStringSliceMap(
		value.ProcessorCategoryOrders,
	)
	value.DefaultKeywords = append([]string(nil), value.DefaultKeywords...)
	return value
}

func cloneStringSliceMap(input map[string][]string) map[string][]string {
	if len(input) == 0 {
		return map[string][]string{}
	}
	result := make(map[string][]string, len(input))
	for key, value := range input {
		result[key] = append([]string(nil), value...)
	}
	return result
}

func cloneNestedMap(input map[string]map[string]any) map[string]map[string]any {
	if len(input) == 0 {
		return map[string]map[string]any{}
	}
	result := make(map[string]map[string]any, len(input))
	for key, value := range input {
		result[key] = cloneAnyMap(value)
	}
	return result
}

func enabledScrapers(input map[string]ScraperConfig) []ScraperConfig {
	scrapers := sortedScrapers(input)
	result := make([]ScraperConfig, 0, len(scrapers))
	for _, scraper := range scrapers {
		if scraper.Enabled {
			result = append(result, scraper)
		}
	}
	return result
}

func sortedScrapers(input map[string]ScraperConfig) []ScraperConfig {
	scrapers := make([]ScraperConfig, 0, len(input))
	for _, scraper := range input {
		scrapers = append(scrapers, cloneScraper(scraper))
	}
	sort.Slice(scrapers, func(i, j int) bool {
		if scrapers[i].Priority != scrapers[j].Priority {
			return scrapers[i].Priority < scrapers[j].Priority
		}
		return scrapers[i].ID < scrapers[j].ID
	})
	return scrapers
}

func normalizeScraper(scraper ScraperConfig) map[string]any {
	keywords := append([]string(nil), scraper.DefaultKeywords...)
	sort.Strings(keywords)
	return map[string]any{
		"id":                        scraper.ID,
		"name":                      scraper.Name,
		"enabled":                   scraper.Enabled,
		"fetcher":                   scraper.Fetcher,
		"hub_root":                  scraper.HubRoot,
		"route":                     scraper.Route,
		"fetch_params":              cloneAnyMap(scraper.FetchParams),
		"priority":                  scraper.Priority,
		"content_processor_configs": cloneNestedMap(scraper.ContentProcessorConfigs),
		"default_keywords":          keywords,
	}
}

func configHash(scrapers []ScraperConfig) (string, error) {
	normalized := make([]map[string]any, 0, len(scrapers))
	for _, scraper := range scrapers {
		value := normalizeScraper(scraper)
		value["content_processor_order"] = append(
			[]string{},
			scraper.ContentProcessorOrder...,
		)
		value["processor_category_orders"] = cloneStringSliceMap(
			scraper.ProcessorCategoryOrders,
		)
		normalized = append(normalized, value)
	}
	payload, err := json.Marshal(normalized)
	if err != nil {
		return "", fmt.Errorf("marshal config hash: %w", err)
	}
	hash := sha256.Sum256(payload)
	return hex.EncodeToString(hash[:]), nil
}

func createVersion(scrapers []ScraperConfig, timestamp time.Time) Version {
	hash, _ := configHash(scrapers)
	return Version{
		ID:            fmt.Sprintf("v%s_%s", timestamp.Format("20060102_150405"), hash[:8]),
		Timestamp:     timestamp,
		ConfigHash:    hash,
		ScrapersCount: len(scrapers),
	}
}

func computeScrapersDiff(previous, current []ScraperConfig) Diff {
	oldMap := make(map[string]map[string]any, len(previous))
	oldConfigs := make(map[string]ScraperConfig, len(previous))
	for _, scraper := range previous {
		oldMap[scraper.ID] = normalizeScraper(scraper)
		oldConfigs[scraper.ID] = scraper
	}
	newMap := make(map[string]map[string]any, len(current))
	newConfigs := make(map[string]ScraperConfig, len(current))
	for _, scraper := range current {
		newMap[scraper.ID] = normalizeScraper(scraper)
		newConfigs[scraper.ID] = scraper
	}
	added := make([]string, 0)
	removed := make([]string, 0)
	modified := make([]ModifiedScraper, 0)
	for id := range newMap {
		if _, ok := oldMap[id]; !ok {
			added = append(added, id)
		}
	}
	for id := range oldMap {
		if _, ok := newMap[id]; !ok {
			removed = append(removed, id)
		}
	}
	sort.Strings(added)
	sort.Strings(removed)
	fieldsOrder := []string{
		"id", "name", "enabled", "fetcher", "hub_root", "route",
		"fetch_params", "priority", "content_processor_configs", "default_keywords",
	}
	for id, before := range oldMap {
		after, ok := newMap[id]
		if !ok {
			continue
		}
		fields := make([]string, 0)
		for _, field := range fieldsOrder {
			if !valuesEqual(before[field], after[field]) {
				fields = append(fields, field)
			}
		}
		beforeConfig := oldConfigs[id]
		afterConfig := newConfigs[id]
		if (!valuesEqual(
			beforeConfig.ContentProcessorOrder,
			afterConfig.ContentProcessorOrder,
		) ||
			!valuesEqual(
				beforeConfig.ProcessorCategoryOrders,
				afterConfig.ProcessorCategoryOrders,
			)) &&
			!slices.Contains(fields, "content_processor_configs") {
			fields = append(fields, "content_processor_configs")
		}
		if len(fields) > 0 {
			modified = append(modified, ModifiedScraper{ID: id, Fields: fields})
		}
	}
	sort.Slice(modified, func(i, j int) bool { return modified[i].ID < modified[j].ID })
	return Diff{Added: added, Removed: removed, Modified: modified}
}

func valuesEqual(left, right any) bool {
	leftJSON, leftErr := json.Marshal(left)
	rightJSON, rightErr := json.Marshal(right)
	if leftErr != nil || rightErr != nil {
		return fmt.Sprint(left) == fmt.Sprint(right)
	}
	return string(leftJSON) == string(rightJSON)
}

func createChangeSummary(diff Diff) string {
	parts := make([]string, 0, 3)
	if len(diff.Added) > 0 {
		parts = append(parts, fmt.Sprintf("added=%v", diff.Added))
	}
	if len(diff.Removed) > 0 {
		parts = append(parts, fmt.Sprintf("removed=%v", diff.Removed))
	}
	if len(diff.Modified) > 0 {
		modified := make([]string, 0, len(diff.Modified))
		for _, item := range diff.Modified {
			modified = append(modified, fmt.Sprintf("%s(%s)", item.ID, strings.Join(item.Fields, ",")))
		}
		parts = append(parts, fmt.Sprintf("modified=%v", modified))
	}
	if len(parts) == 0 {
		return "Configuration updated"
	}
	return strings.Join(parts, "; ")
}

func formatErrors(fileErrors map[string]string) string {
	if len(fileErrors) == 0 {
		return ""
	}
	paths := make([]string, 0, len(fileErrors))
	for path := range fileErrors {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	parts := make([]string, 0, len(paths))
	for _, path := range paths {
		parts = append(parts, fmt.Sprintf("%s: %s", path, fileErrors[path]))
	}
	return strings.Join(parts, "; ")
}

func copyVersion(version *Version) *Version {
	if version == nil {
		return nil
	}
	copy := *version
	return &copy
}

func copyDiff(diff *Diff) *Diff {
	if diff == nil {
		return nil
	}
	copy := *diff
	copy.Added = append([]string(nil), diff.Added...)
	copy.Removed = append([]string(nil), diff.Removed...)
	copy.Modified = make([]ModifiedScraper, len(diff.Modified))
	for index, modified := range diff.Modified {
		copy.Modified[index] = ModifiedScraper{
			ID:     modified.ID,
			Fields: append([]string(nil), modified.Fields...),
		}
	}
	return &copy
}
