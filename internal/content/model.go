package content

// Content is the canonical item exchanged by fetchers, processors, and storage.
type Content struct {
	ContentID   string   `json:"content_id"`
	Title       string   `json:"title"`
	Link        string   `json:"link"`
	Summary     string   `json:"summary"`
	Content     string   `json:"content"`
	Published   string   `json:"published"`
	Author      *string  `json:"author,omitempty"`
	Keywords    []string `json:"keywords,omitempty"`
	Tags        []string `json:"tags,omitempty"`
	ScraperName *string  `json:"scraper_name,omitempty"`
}
