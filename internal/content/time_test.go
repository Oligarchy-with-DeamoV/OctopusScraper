package content

import (
	"testing"
	"time"
)

func TestParsePublishedTimeNormalizesSupportedValues(t *testing.T) {
	for _, value := range []string{
		"2026-08-18T11:00:00Z",
		"Tue, 18 Aug 2026 11:00:00 +0000",
		"2026-08-18 19:00:00 +0800",
		"2026-08-18",
	} {
		parsed, ok := ParsePublishedTime(value)
		if !ok || parsed.Location() != time.UTC {
			t.Fatalf("ParsePublishedTime(%q) = %v, %t", value, parsed, ok)
		}
	}
	if _, ok := ParsePublishedTime("not-a-time"); ok {
		t.Fatal("expected invalid publication time to be rejected")
	}
}

func TestParsePublishedTimeNamedZones(t *testing.T) {
	tests := []struct {
		value string
		want  string
		ok    bool
	}{
		{
			value: "Tue, 18 Aug 2026 11:00:00 PST",
			want:  "2026-08-18T19:00:00Z",
			ok:    true,
		},
		{
			value: "18 Aug 26 11:00 PST",
			want:  "2026-08-18T19:00:00Z",
			ok:    true,
		},
		{
			value: "Tuesday, 18-Aug-26 11:00:00 PST",
			want:  "2026-08-18T19:00:00Z",
			ok:    true,
		},
		{
			value: "Tue Aug 18 11:00:00 -0800 2026",
			want:  "2026-08-18T19:00:00Z",
			ok:    true,
		},
		{
			value: "2026-08-18 11:00:00 -0800 PST",
			want:  "2026-08-18T19:00:00Z",
			ok:    true,
		},
		{
			value: "2026-08-18 11:00:00 +0200 CEST",
			want:  "2026-08-18T09:00:00Z",
			ok:    true,
		},
		{
			value: "2026-08-18 11:00:00 +0800 CST",
			want:  "2026-08-18T03:00:00Z",
			ok:    true,
		},
		{
			value: "Tue Aug 18 11:00:00 2026",
			want:  "2026-08-18T11:00:00Z",
			ok:    true,
		},
		{
			value: "Tue, 18 Aug 2026 11:00:00 XYZ",
			ok:    false,
		},
		{
			value: "2026-08-18 11:00:00 +0000 XYZ",
			want:  "2026-08-18T11:00:00Z",
			ok:    true,
		},
	}
	for _, test := range tests {
		parsed, ok := ParsePublishedTime(test.value)
		if ok != test.ok {
			t.Fatalf("ParsePublishedTime(%q) ok = %t, want %t", test.value, ok, test.ok)
		}
		if test.ok && parsed.Format(time.RFC3339) != test.want {
			t.Fatalf("ParsePublishedTime(%q) = %s, want %s",
				test.value, parsed.Format(time.RFC3339), test.want)
		}
	}
}
