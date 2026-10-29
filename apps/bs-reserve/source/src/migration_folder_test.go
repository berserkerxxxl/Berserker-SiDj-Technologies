package main

import (
	"archive/zip"
	"bytes"
	"context"
	"encoding/json"
	"io"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestMigrationSelectedDirectory(t *testing.T) {
	s := newTestStore(t)
	if _, err := s.ImportFile(jsonFile(t, fixture("external", "Данные остаются целыми", 1700000010), "raw.json")); err != nil {
		t.Fatal(err)
	}
	// Model an unavailable default Outbox: selecting another volume must not
	// create any temporary or final ZIP there.
	outbox := filepath.Join(s.Root, "Outbox")
	if err := os.Remove(outbox); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(outbox, []byte("unavailable"), 0600); err != nil {
		t.Fatal(err)
	}
	directory := filepath.Join(t.TempDir(), "Другая папка с пробелами")
	result, err := s.MigrationTo(directory)
	if err != nil {
		t.Fatal(err)
	}
	item := result.(map[string]any)
	if item["Path"].(string) != filepath.Join(directory, item["Name"].(string)) {
		t.Fatal("selected directory ignored")
	}
	sha, _, err := hashFile(item["Path"].(string))
	if err != nil || sha != item["SHA256"] {
		t.Fatal("archive hash mismatch", err)
	}
	reader, err := zip.OpenReader(item["Path"].(string))
	if err != nil {
		t.Fatal(err)
	}
	defer reader.Close()
	for _, entry := range reader.File {
		f, e := entry.Open()
		if e != nil {
			t.Fatal(e)
		}
		_, e = io.Copy(io.Discard, f)
		f.Close()
		if e != nil {
			t.Fatal(e)
		}
	}
	if temps, _ := filepath.Glob(filepath.Join(directory, ".migration-*")); len(temps) != 0 {
		t.Fatal("temporary archive left behind")
	}
	for _, invalid := range []string{"relative-path", filepath.Join(s.Vault, "nested-output"), outbox} {
		if _, err := s.MigrationTo(invalid); err == nil {
			t.Fatal("invalid destination accepted", invalid)
		}
	}
	if checked := s.Verify(); len(checked.Errors) != 0 {
		t.Fatal("export failures modified source archive", checked.Errors)
	}
}

func TestMigrationDownloadSelectedDirectory(t *testing.T) {
	s := newTestStore(t)
	_, err := s.ImportFile(jsonFile(t, fixture("download", "Полный пакет", 1700000010), "raw.json"))
	if err != nil {
		t.Fatal(err)
	}
	a := &App{store: s, token: "synthetic-test-token", seen: map[string]string{}}
	directory := filepath.Join(t.TempDir(), "Другой диск")
	body, _ := json.Marshal(ActionRequest{Action: "migration", Target: directory})
	req := httptest.NewRequest("POST", "http://127.0.0.1:1234/api/action", bytes.NewReader(body))
	req.Header.Set("X-BS-Token", a.token)
	w := httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	if w.Code != 200 {
		t.Fatal(w.Code, w.Body.String())
	}
	var result map[string]any
	deadline := time.Now().Add(5 * time.Second)
	for time.Now().Before(deadline) {
		a.mu.Lock()
		job := a.job
		a.mu.Unlock()
		if !job.Running {
			if job.Error != "" {
				t.Fatal(job.Error)
			}
			result = job.Result.(map[string]any)
			break
		}
		time.Sleep(time.Millisecond)
	}
	if result == nil {
		t.Fatal("migration job did not complete")
	}
	name := result["Name"].(string)
	a.mu.Lock()
	a.job = Job{} // A later operation must not revoke the generated download.
	a.mu.Unlock()
	query := "http://127.0.0.1:1234/api/download?name=" + url.QueryEscape(name)
	req = httptest.NewRequest("GET", query, nil)
	req.Header.Set("X-BS-Token", a.token)
	w = httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	if w.Code != 200 || sum(w.Body.Bytes()) != result["SHA256"] {
		t.Fatal("external archive download failed", w.Code)
	}
	if loadConfig(s.Root).MigrationDirectory != directory {
		t.Fatal("chosen destination not remembered")
	}
	req = httptest.NewRequest("GET", query, nil)
	w = httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	if w.Code != 403 {
		t.Fatal("download bypassed token boundary")
	}
}

func TestFolderPickerAPI(t *testing.T) {
	selected := filepath.Join(t.TempDir(), "Папка O'Brien")
	called := false
	a := &App{token: "synthetic-picker-token", picker: func(ctx context.Context, initial string) (string, error) {
		called = true
		return selected, nil
	}}
	req := httptest.NewRequest("POST", "http://127.0.0.1:1234/api/pick-folder", bytes.NewBufferString(`{"Initial":""}`))
	w := httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	if w.Code != 403 || called {
		t.Fatal("remote page could open folder dialog")
	}
	req = httptest.NewRequest("POST", "http://127.0.0.1:1234/api/pick-folder", bytes.NewBufferString(`{"Initial":""}`))
	req.Header.Set("X-BS-Token", a.token)
	w = httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	var result struct {
		Path      string
		Cancelled bool
	}
	if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil || result.Path != selected || result.Cancelled {
		t.Fatal("selected path not returned intact", w.Code, err)
	}
	a.picker = func(context.Context, string) (string, error) { return "", nil }
	req = httptest.NewRequest("POST", "http://127.0.0.1:1234/api/pick-folder", bytes.NewBufferString(`{"Initial":""}`))
	req.Header.Set("X-BS-Token", a.token)
	w = httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	if err := json.Unmarshal(w.Body.Bytes(), &result); err != nil || !result.Cancelled || result.Path != "" {
		t.Fatal("cancelling folder dialog changed selection", err)
	}
}

func TestScheduleTimeValidation(t *testing.T) {
	for _, value := range []string{"00:00", "06:30", "19:00", "23:59"} {
		if err := validateScheduleTime(value); err != nil {
			t.Fatal(value, err)
		}
	}
	for _, value := range []string{"", "6:30", "24:00", "19:60", "19:00;calc", "12:00:00"} {
		if validateScheduleTime(value) == nil {
			t.Fatal("invalid schedule accepted", value)
		}
	}
}
