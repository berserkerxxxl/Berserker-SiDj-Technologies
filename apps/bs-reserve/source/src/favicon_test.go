package main

import (
	"bytes"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestFaviconServedAndEmbedded(t *testing.T) {
	if len(faviconICO) < 1024 || !bytes.Equal(faviconICO[:4], []byte{0, 0, 1, 0}) {
		t.Fatal("missing or invalid embedded Windows icon")
	}
	a := &App{token: "synthetic-favicon-token"}
	w := httptest.NewRecorder()
	r := httptest.NewRequest(http.MethodGet, "http://127.0.0.1:4567/favicon.ico", nil)
	a.handler().ServeHTTP(w, r)
	if w.Code != http.StatusOK || w.Header().Get("Content-Type") != "image/x-icon" || !bytes.Equal(w.Body.Bytes(), faviconICO) {
		t.Fatalf("favicon endpoint: status=%d content-type=%q", w.Code, w.Header().Get("Content-Type"))
	}
	w = httptest.NewRecorder()
	a.handler().ServeHTTP(w, httptest.NewRequest(http.MethodGet, "http://127.0.0.1:4567/", nil))
	if w.Code != http.StatusOK || !strings.Contains(w.Body.String(), "favicon.ico") {
		t.Fatalf("favicon missing from page: %d", w.Code)
	}
	if !strings.Contains(offlineHTML, "favicon.ico") {
		t.Fatal("offline archive favicon link missing")
	}
	if !strings.Contains(uiHTML, "renderArchiveText(m.Text") || !strings.Contains(offlineHTML, "renderArchiveText(m.Text") {
		t.Fatal("chat text link rendering missing")
	}
}
