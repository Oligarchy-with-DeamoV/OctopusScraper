package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

const testChangelog = `# Changelog

## [Unreleased]

### Changed
- Existing change

### Removed
- Existing removal

## [0.2.0] - 2025-05-07

### Added
- Initial entry
`

func TestReleaseAggregatesFragmentsAndExistingEntries(t *testing.T) {
	t.Parallel()

	root := newTestRepository(t)
	writeTestFile(t, root, "changelog.d/200.fixed.md", "Second fix\n")
	writeTestFile(t, root, "changelog.d/100.added.md", "First addition\n")

	err := release(root, "0.3.0", time.Date(2026, 8, 19, 10, 0, 0, 0, time.UTC))
	if err != nil {
		t.Fatal(err)
	}
	content := readTestFile(t, root, changelogName)
	expected := `# Changelog

## [Unreleased]

## [0.3.0] - 2026-08-19

### Added
- First addition

### Changed
- Existing change

### Fixed
- Second fix

### Removed
- Existing removal

## [0.2.0] - 2025-05-07

### Added
- Initial entry
`
	if content != expected {
		t.Fatalf("CHANGELOG.md:\n%s\nwant:\n%s", content, expected)
	}
	for _, name := range []string{"changelog.d/100.added.md", "changelog.d/200.fixed.md"} {
		if _, err := os.Stat(filepath.Join(root, name)); !os.IsNotExist(err) {
			t.Fatalf("%s still exists or stat failed: %v", name, err)
		}
	}
	if _, err := os.Stat(filepath.Join(root, "changelog.d/.gitkeep")); err != nil {
		t.Fatalf(".gitkeep: %v", err)
	}
}

func TestReadFragmentsRejectsInvalidFiles(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		path    string
		content string
		want    string
	}{
		{name: "invalid name", path: "bad.md", content: "text", want: "invalid changelog fragment name"},
		{name: "unknown type", path: "100.docs.md", content: "text", want: "invalid changelog fragment name"},
		{name: "empty", path: "100.fixed.md", content: " \n", want: "is empty"},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			root := newTestRepository(t)
			writeTestFile(t, root, filepath.Join(fragmentsName, test.path), test.content)
			_, err := readFragments(root)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("readFragments error = %v, want %q", err, test.want)
			}
		})
	}
}

func TestReleaseValidationDoesNotModifyFiles(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name    string
		version string
		setup   func(*testing.T, string)
		want    string
	}{
		{
			name:    "empty version",
			version: "",
			setup: func(t *testing.T, root string) {
				writeTestFile(t, root, "changelog.d/100.fixed.md", "Fix")
			},
			want: "must match",
		},
		{
			name:    "invalid version",
			version: "v0.3.0",
			setup: func(t *testing.T, root string) {
				writeTestFile(t, root, "changelog.d/100.fixed.md", "Fix")
			},
			want: "must match",
		},
		{
			name:    "existing version",
			version: "0.2.0",
			setup: func(t *testing.T, root string) {
				writeTestFile(t, root, "changelog.d/100.fixed.md", "Fix")
			},
			want: "already contains",
		},
		{
			name:    "no fragments",
			version: "0.3.0",
			setup:   func(*testing.T, string) {},
			want:    "no changelog fragments",
		},
	}
	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			root := newTestRepository(t)
			test.setup(t, root)
			before := readTestFile(t, root, changelogName)

			err := release(root, test.version, time.Now())
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("release error = %v, want %q", err, test.want)
			}
			if after := readTestFile(t, root, changelogName); after != before {
				t.Fatalf("CHANGELOG.md changed after validation error")
			}
			if test.version != "0.3.0" || test.name != "no fragments" {
				if _, statErr := os.Stat(filepath.Join(root, "changelog.d/100.fixed.md")); statErr != nil {
					t.Fatalf("fragment removed after validation error: %v", statErr)
				}
			}
		})
	}
}

func TestRunRejectsUnknownCommandAndArguments(t *testing.T) {
	t.Parallel()

	now := func() time.Time { return time.Unix(0, 0) }
	for _, arguments := range [][]string{
		nil,
		{"unknown"},
		{"check", "extra"},
		{"release", "--version", "0.3.0", "extra"},
	} {
		if err := run(arguments, now); err == nil {
			t.Fatalf("run(%v) succeeded", arguments)
		}
	}
}

func TestRestoreFragmentsPreservesContentAndMode(t *testing.T) {
	t.Parallel()

	root := newTestRepository(t)
	path := filepath.Join(root, "changelog.d/100.fixed.md")
	content := []byte("Preserve  spacing\nand lines\n")
	if err := os.WriteFile(path, content, 0o640); err != nil {
		t.Fatal(err)
	}
	fragments, err := readFragments(root)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err := restoreFragments(fragments); err != nil {
		t.Fatal(err)
	}
	restored, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if string(restored) != string(content) {
		t.Fatalf("restored content = %q, want %q", restored, content)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0o640 {
		t.Fatalf("restored mode = %v, want 0640", info.Mode().Perm())
	}
}

func newTestRepository(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	if err := os.Mkdir(filepath.Join(root, fragmentsName), 0o755); err != nil {
		t.Fatal(err)
	}
	writeTestFile(t, root, changelogName, testChangelog)
	writeTestFile(t, root, "changelog.d/.gitkeep", "")
	return root
}

func writeTestFile(t *testing.T, root, name, content string) {
	t.Helper()
	path := filepath.Join(root, name)
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func readTestFile(t *testing.T, root, name string) string {
	t.Helper()
	content, err := os.ReadFile(filepath.Join(root, name))
	if err != nil {
		t.Fatal(err)
	}
	return string(content)
}
