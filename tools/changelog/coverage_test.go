package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestRunSuccessfulCommands(t *testing.T) {
	root := newTestRepository(t)
	writeTestFile(t, root, "changelog.d/100.fixed.md", "Fix")
	now := func() time.Time { return time.Date(2026, 8, 30, 0, 0, 0, 0, time.UTC) }
	if err := run([]string{"check", "--root", root}, now); err != nil {
		t.Fatal(err)
	}
	if err := run([]string{"release", "--root", root, "--version", "0.3.0"}, now); err != nil {
		t.Fatal(err)
	}
}

func TestReadFragmentsFilesystemErrors(t *testing.T) {
	t.Run("missing directory", func(t *testing.T) {
		if _, err := readFragments(t.TempDir()); err == nil ||
			!strings.Contains(err.Error(), "read changelog fragments") {
			t.Fatalf("missing directory error = %v", err)
		}
	})
	t.Run("directory fragment", func(t *testing.T) {
		root := newTestRepository(t)
		if err := os.Mkdir(filepath.Join(root, fragmentsName, "100.fixed.md"), 0o755); err != nil {
			t.Fatal(err)
		}
		if _, err := readFragments(root); err == nil ||
			!strings.Contains(err.Error(), "must be a file") {
			t.Fatalf("directory fragment error = %v", err)
		}
	})
	t.Run("unreadable target", func(t *testing.T) {
		root := newTestRepository(t)
		if err := os.Symlink("missing-target", filepath.Join(root, fragmentsName, "100.fixed.md")); err != nil {
			t.Fatal(err)
		}
		if _, err := readFragments(root); err == nil ||
			!strings.Contains(err.Error(), "read changelog fragment") {
			t.Fatalf("unreadable fragment error = %v", err)
		}
	})
}

func TestBuildChangelogRejectsInvalidStructure(t *testing.T) {
	fragments := []fragment{{section: "fixed", entry: "- fix"}}
	tests := []struct {
		name string
		text string
		want string
	}{
		{"duplicate", testChangelog + "\n## [0.3.0] - 2026-01-01\n", "already contains"},
		{"missing unreleased", "# Changelog\n\n## [0.2.0]\n", "no [Unreleased]"},
		{"missing version", "## [Unreleased]\n", "no version section"},
		{"unsupported section", "#\n## [Unreleased]\n\n### Other\n- x\n\n## [0.2.0]\n", "unsupported"},
		{"outside section", "#\n## [Unreleased]\n\norphan\n\n## [0.2.0]\n", "outside"},
		{"invalid entry", "#\n## [Unreleased]\n\n### Fixed\ntext\n\n## [0.2.0]\n", "invalid entry"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			if _, err := buildChangelog(test.text, "0.3.0", time.Now(), fragments); err == nil ||
				!strings.Contains(err.Error(), test.want) {
				t.Fatalf("buildChangelog error = %v, want %q", err, test.want)
			}
		})
	}
}

func TestParseSectionsHandlesMultilineAndErrors(t *testing.T) {
	sections, err := parseSections("### Fixed\n- first\n  continuation\n### Added\n- second")
	if err != nil || len(sections["fixed"]) != 1 ||
		sections["fixed"][0] != "- first\n  continuation" {
		t.Fatalf("parsed sections = %#v, %v", sections, err)
	}
	for _, test := range []struct {
		body string
		want string
	}{
		{"### Other\n- x", "unsupported"},
		{"orphan", "outside"},
		{"### Fixed\ntext", "invalid entry"},
		{"### Fixed\n- one\ntext\n### Fixed\ntext", "invalid entry"},
	} {
		if _, err := parseSections(test.body); err == nil ||
			!strings.Contains(err.Error(), test.want) {
			t.Fatalf("parseSections(%q) = %v", test.body, err)
		}
	}
}

func TestPrepareAndRestoreFilesystemErrors(t *testing.T) {
	if _, err := prepareFile(filepath.Join(t.TempDir(), "missing", "CHANGELOG.md"), nil, 0o644); err == nil ||
		!strings.Contains(err.Error(), "create temporary changelog") {
		t.Fatalf("prepareFile error = %v", err)
	}
	item := fragment{
		path:    filepath.Join(t.TempDir(), "missing", "fragment.md"),
		content: []byte("fragment"),
		mode:    0o644,
	}
	if err := restoreFragments([]fragment{item}); err == nil ||
		!strings.Contains(err.Error(), "restore") {
		t.Fatalf("restoreFragments error = %v", err)
	}
}

func TestReleaseFilesystemErrors(t *testing.T) {
	root := newTestRepository(t)
	writeTestFile(t, root, "changelog.d/100.fixed.md", "Fix")
	if err := os.Remove(filepath.Join(root, changelogName)); err != nil {
		t.Fatal(err)
	}
	if err := release(root, "0.3.0", time.Now()); err == nil ||
		!strings.Contains(err.Error(), "read changelog") {
		t.Fatalf("release missing changelog error = %v", err)
	}
}

func TestRunRejectsInvalidFlags(t *testing.T) {
	t.Run("check flag error", func(t *testing.T) {
		if err := run([]string{"check", "--unknown"}, time.Now); err == nil {
			t.Fatal("expected flag parsing error")
		}
		if err := run([]string{"release", "--unknown"}, time.Now); err == nil {
			t.Fatal("expected release flag parsing error")
		}
	})
}
