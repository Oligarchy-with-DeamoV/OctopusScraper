package processor

import (
	"fmt"
	"io"
)

func readBoundedBody(reader io.Reader, maxBytes int64) ([]byte, error) {
	limited := &io.LimitedReader{R: reader, N: maxBytes + 1}
	body, err := io.ReadAll(limited)
	if err != nil {
		return nil, err
	}
	if int64(len(body)) > maxBytes {
		return nil, fmt.Errorf("response body exceeds %d bytes", maxBytes)
	}
	return body, nil
}
