package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"time"
)

const (
	changelogName = "CHANGELOG.md"
	fragmentsName = "changelog.d"
)

var (
	versionPattern  = regexp.MustCompile(`^[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?$`)
	fragmentPattern = regexp.MustCompile(`^([A-Za-z0-9][A-Za-z0-9_-]*)\.(added|changed|fixed|removed|security)\.md$`)
	sectionOrder    = []string{"added", "changed", "fixed", "removed", "security"}
	sectionTitles   = map[string]string{
		"added":    "Added",
		"changed":  "Changed",
		"fixed":    "Fixed",
		"removed":  "Removed",
		"security": "Security",
	}
)

type fragment struct {
	path    string
	section string
	entry   string
	content []byte
	mode    os.FileMode
}

func main() {
	if err := run(os.Args[1:], time.Now); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(arguments []string, now func() time.Time) error {
	if len(arguments) == 0 {
		return errors.New("usage: changelog check|release")
	}
	switch arguments[0] {
	case "check":
		flags := flag.NewFlagSet("check", flag.ContinueOnError)
		root := flags.String("root", ".", "repository root")
		if err := flags.Parse(arguments[1:]); err != nil {
			return err
		}
		if flags.NArg() != 0 {
			return fmt.Errorf("unexpected check arguments: %v", flags.Args())
		}
		_, err := readFragments(*root)
		return err
	case "release":
		flags := flag.NewFlagSet("release", flag.ContinueOnError)
		root := flags.String("root", ".", "repository root")
		version := flags.String("version", "", "release version without v prefix")
		if err := flags.Parse(arguments[1:]); err != nil {
			return err
		}
		if flags.NArg() != 0 {
			return fmt.Errorf("unexpected release arguments: %v", flags.Args())
		}
		return release(*root, *version, now().UTC())
	default:
		return fmt.Errorf("unknown changelog command %q", arguments[0])
	}
}

func readFragments(root string) ([]fragment, error) {
	directory := filepath.Join(root, fragmentsName)
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, fmt.Errorf("read changelog fragments: %w", err)
	}
	fragments := make([]fragment, 0, len(entries))
	for _, entry := range entries {
		if entry.Name() == ".gitkeep" {
			continue
		}
		if entry.IsDir() {
			return nil, fmt.Errorf("changelog fragment %q must be a file", entry.Name())
		}
		matches := fragmentPattern.FindStringSubmatch(entry.Name())
		if matches == nil {
			return nil, fmt.Errorf("invalid changelog fragment name %q", entry.Name())
		}
		path := filepath.Join(directory, entry.Name())
		content, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read changelog fragment %q: %w", entry.Name(), err)
		}
		info, err := entry.Info()
		if err != nil {
			return nil, fmt.Errorf("stat changelog fragment %q: %w", entry.Name(), err)
		}
		text := strings.Join(strings.Fields(string(content)), " ")
		if text == "" {
			return nil, fmt.Errorf("changelog fragment %q is empty", entry.Name())
		}
		fragments = append(fragments, fragment{
			path:    path,
			section: matches[2],
			entry:   "- " + text,
			content: content,
			mode:    info.Mode().Perm(),
		})
	}
	sort.Slice(fragments, func(i, j int) bool {
		return fragments[i].path < fragments[j].path
	})
	return fragments, nil
}

func release(root, version string, now time.Time) error {
	if !versionPattern.MatchString(version) {
		return fmt.Errorf("version %q must match x.y.z or x.y.z-rc.N", version)
	}
	fragments, err := readFragments(root)
	if err != nil {
		return err
	}
	if len(fragments) == 0 {
		return errors.New("no changelog fragments to release")
	}

	path := filepath.Join(root, changelogName)
	current, err := os.ReadFile(path)
	if err != nil {
		return fmt.Errorf("read changelog: %w", err)
	}
	updated, err := buildChangelog(string(current), version, now, fragments)
	if err != nil {
		return err
	}
	info, err := os.Stat(path)
	if err != nil {
		return fmt.Errorf("stat changelog: %w", err)
	}
	temporary, err := prepareFile(path, []byte(updated), info.Mode())
	if err != nil {
		return err
	}
	defer os.Remove(temporary)

	removed := make([]fragment, 0, len(fragments))
	for _, item := range fragments {
		if err := os.Remove(item.path); err != nil {
			restoreErr := restoreFragments(removed)
			if restoreErr != nil {
				return fmt.Errorf("remove fragment %q: %w; restore fragments: %v", filepath.Base(item.path), err, restoreErr)
			}
			return fmt.Errorf("remove fragment %q: %w", filepath.Base(item.path), err)
		}
		removed = append(removed, item)
	}
	if err := os.Rename(temporary, path); err != nil {
		restoreErr := restoreFragments(removed)
		if restoreErr != nil {
			return fmt.Errorf("replace changelog: %w; restore fragments: %v", err, restoreErr)
		}
		return fmt.Errorf("replace changelog: %w", err)
	}
	return nil
}

func buildChangelog(
	current string,
	version string,
	now time.Time,
	fragments []fragment,
) (string, error) {
	versionHeading := "## [" + version + "]"
	if strings.Contains(current, versionHeading+" ") ||
		strings.Contains(current, versionHeading+"\n") {
		return "", fmt.Errorf("changelog already contains version %s", version)
	}

	const unreleasedHeading = "## [Unreleased]"
	start := strings.Index(current, unreleasedHeading)
	if start < 0 {
		return "", errors.New("changelog has no [Unreleased] section")
	}
	bodyStart := start + len(unreleasedHeading)
	nextOffset := strings.Index(current[bodyStart:], "\n## [")
	if nextOffset < 0 {
		return "", errors.New("changelog has no version section after [Unreleased]")
	}
	next := bodyStart + nextOffset
	existing, err := parseSections(current[bodyStart:next])
	if err != nil {
		return "", err
	}
	for _, item := range fragments {
		existing[item.section] = append(existing[item.section], item.entry)
	}

	var section strings.Builder
	fmt.Fprintf(&section, "## [%s] - %s\n", version, now.Format("2006-01-02"))
	for _, name := range sectionOrder {
		entries := existing[name]
		if len(entries) == 0 {
			continue
		}
		fmt.Fprintf(&section, "\n### %s\n", sectionTitles[name])
		for _, entry := range entries {
			section.WriteString(entry)
			section.WriteByte('\n')
		}
	}

	prefix := strings.TrimRight(current[:start], "\n")
	suffix := strings.TrimLeft(current[next:], "\n")
	return prefix + "\n\n" + unreleasedHeading + "\n\n" +
		section.String() + "\n" + suffix, nil
}

func parseSections(body string) (map[string][]string, error) {
	sections := make(map[string][]string, len(sectionOrder))
	titleToName := make(map[string]string, len(sectionOrder))
	for name, title := range sectionTitles {
		titleToName["### "+title] = name
	}

	currentSection := ""
	currentEntry := ""
	flush := func() {
		if currentEntry != "" {
			sections[currentSection] = append(sections[currentSection], currentEntry)
			currentEntry = ""
		}
	}
	for _, line := range strings.Split(strings.TrimSpace(body), "\n") {
		line = strings.TrimRight(line, " \t\r")
		if line == "" {
			continue
		}
		if name, ok := titleToName[line]; ok {
			flush()
			currentSection = name
			continue
		}
		if strings.HasPrefix(line, "### ") {
			return nil, fmt.Errorf("unsupported [Unreleased] section %q", strings.TrimPrefix(line, "### "))
		}
		if currentSection == "" {
			return nil, fmt.Errorf("content outside a supported [Unreleased] section: %q", line)
		}
		if strings.HasPrefix(line, "- ") {
			flush()
			currentEntry = line
			continue
		}
		if currentEntry == "" {
			return nil, fmt.Errorf("invalid entry in [Unreleased] section %q", line)
		}
		currentEntry += "\n" + line
	}
	flush()
	return sections, nil
}

func prepareFile(path string, content []byte, mode os.FileMode) (string, error) {
	file, err := os.CreateTemp(filepath.Dir(path), "."+filepath.Base(path)+".*")
	if err != nil {
		return "", fmt.Errorf("create temporary changelog: %w", err)
	}
	name := file.Name()
	cleanup := func() {
		file.Close()
		os.Remove(name)
	}
	if err := file.Chmod(mode); err != nil {
		cleanup()
		return "", fmt.Errorf("set temporary changelog mode: %w", err)
	}
	if _, err := file.Write(content); err != nil {
		cleanup()
		return "", fmt.Errorf("write temporary changelog: %w", err)
	}
	if err := file.Sync(); err != nil {
		cleanup()
		return "", fmt.Errorf("sync temporary changelog: %w", err)
	}
	if err := file.Close(); err != nil {
		os.Remove(name)
		return "", fmt.Errorf("close temporary changelog: %w", err)
	}
	return name, nil
}

func restoreFragments(fragments []fragment) error {
	var failures []error
	for _, item := range fragments {
		if err := os.WriteFile(item.path, item.content, item.mode); err != nil {
			failures = append(failures, fmt.Errorf("restore %q: %w", filepath.Base(item.path), err))
		}
	}
	return errors.Join(failures...)
}
