package main

import (
	"encoding/json"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestScheduledForwardingWaitsForCompletionAndReportsFailure(t *testing.T) {
	s := newTestStore(t)
	a := &App{store: s, token: strings.Repeat("e", 48), seen: map[string]string{},
		cfg: Config{WatchEnabled: false, AutoBackup: true, Repository: filepath.Join(t.TempDir(), "absent-repo")}}
	server := httptest.NewServer(a.handler())
	defer server.Close()
	if err := os.WriteFile(filepath.Join(s.Root, "server-address.txt"), []byte(server.URL), 0600); err != nil {
		t.Fatal(err)
	}
	err := forwardRunOnce(s.Root)
	if err == nil {
		t.Fatal("scheduled request did not report actual failure")
	}
	cfg := loadConfig(s.Root)
	if cfg.AutoLastOutcome != "error" || cfg.AutoLastAttempt == "" || cfg.AutoLastFailure == "" || cfg.AutoLastError == "" {
		b, _ := json.Marshal(cfg)
		t.Fatalf("failed run was not stored: %s", b)
	}
}

func TestRunOnceScanOnlyStatusPersisted(t *testing.T) {
	s := newTestStore(t)
	a := &App{store: s, token: strings.Repeat("a", 48), cfg: Config{WatchEnabled: false}, seen: map[string]string{}}
	if err := a.runOnce(); err != nil {
		t.Fatal(err)
	}
	cfg := loadConfig(s.Root)
	if cfg.AutoLastOutcome != "scan-only" || cfg.AutoLastAttempt == "" || cfg.AutoLastSuccess != "" {
		t.Fatalf("scan-only should not be a successful encrypted backup: %+v", cfg)
	}
}
