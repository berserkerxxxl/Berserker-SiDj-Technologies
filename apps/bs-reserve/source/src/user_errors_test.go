package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type testExitCode int

func (e testExitCode) Error() string { return fmt.Sprintf("exit status %d", e) }
func (e testExitCode) ExitCode() int { return int(e) }

func TestRussianExternalErrors(t *testing.T) {
	for _, item := range []struct {
		Error    error
		Contains string
	}{
		{&os.PathError{Op: "open", Path: "synthetic.txt", Err: os.ErrNotExist}, "не найдены"},
		{fmt.Errorf("wrapped: %w", &os.PathError{Op: "write", Path: "synthetic.txt", Err: os.ErrPermission}), "Нет доступа"},
		{errors.New("write C:\\Проверка\\file: There is not enough space on the disk."), "Недостаточно свободного места"},
		{errors.New("read-only file system"), "защищён от записи"},
		{errors.New("external error involving Папка"), "Не удалось выполнить операцию"},
		{fmt.Errorf("русский контекст: %w", errors.New("unknown external failure")), "Не удалось выполнить операцию"},
		{errors.New("пароли не совпали"), "пароли не совпали"},
	} {
		if got := userError(item.Error); !strings.Contains(got, item.Contains) || strings.Contains(got, "There is not") || strings.Contains(got, "external error") {
			t.Fatal("untranslated or incorrect explanation", got)
		}
	}
	var value any
	err := json.Unmarshal([]byte(`{"broken":`), &value)
	if !strings.Contains(userError(err), "JSON") {
		t.Fatal("JSON parser error was not explained")
	}
}

func TestResticExitCodesInRussian(t *testing.T) {
	for code, word := range map[int]string{3: "не полностью", 10: "не найден", 11: "заблокирован", 12: "Неверный пароль"} {
		raw := &resticError{Cause: testExitCode(code), Output: "synthetic private technical output"}
		wrapped := fmt.Errorf("operation: %w", raw)
		if got := userError(wrapped); !strings.Contains(got, word) || strings.Contains(got, raw.Output) {
			t.Fatal(code, got)
		}
		var cause interface{ ExitCode() int }
		if !errors.As(wrapped, &cause) || cause.ExitCode() != code {
			t.Fatal("lost engine exit code")
		}
	}
	err := &resticError{Cause: testExitCode(1), Output: "no space left on device"}
	if !strings.Contains(userError(err), "Недостаточно свободного места") {
		t.Fatal("engine disk-full error hidden by generic failure")
	}
}

func TestRussianJobAndAPIPreserveDiagnostics(t *testing.T) {
	s := newTestStore(t)
	a := &App{store: s, token: "synthetic-error-token"}
	request := httptest.NewRequest("GET", "http://127.0.0.1:1234/api/state", nil)
	denied := httptest.NewRecorder()
	a.handler().ServeHTTP(denied, request)
	if denied.Code != 403 {
		t.Fatal("unauthenticated API access allowed")
	}
	if _, err := os.Stat(filepath.Join(s.Root, "logs", "operations.jsonl")); !os.IsNotExist(err) {
		t.Fatal("unauthenticated request wrote to the archive journal", err)
	}

	raw := &os.PathError{Op: "write", Path: filepath.Join(s.Vault, "objects", ".incoming-test"), Err: errors.New("There is not enough space on the disk.")}
	if err := a.startJob("folder", func() (any, error) { return nil, raw }); err != nil {
		t.Fatal(err)
	}
	deadline := time.Now().Add(2 * time.Second)
	var log []byte
	for time.Now().Before(deadline) {
		a.logMu.Lock()
		log, _ = os.ReadFile(filepath.Join(s.Root, "logs", "operations.jsonl"))
		a.logMu.Unlock()
		if bytes.Contains(log, []byte(`"Details"`)) {
			break
		}
		time.Sleep(time.Millisecond)
	}
	a.mu.Lock()
	job := a.job
	a.mu.Unlock()
	if job.Running || !strings.Contains(job.Error, "Недостаточно свободного места") || strings.Contains(job.Error, "There is not") {
		t.Fatal("job exposes raw error", job)
	}
	if !bytes.Contains(log, []byte("There is not enough space")) || !bytes.Contains(log, []byte("Недостаточно свободного места")) {
		t.Fatal("diagnostic log lost original or translated message")
	}
	response := httptest.NewRecorder()
	a.fail(response, 500, raw)
	var result struct{ Error string }
	if err := json.Unmarshal(response.Body.Bytes(), &result); err != nil || !strings.Contains(result.Error, "Недостаточно свободного места") || strings.Contains(result.Error, "There is not") {
		t.Fatal("API exposes raw error", err, result)
	}
	if !strings.Contains(response.Header().Get("Content-Type"), "application/json") {
		t.Fatal("error response has wrong content type")
	}
}

func TestLegacyErrorJournalTranslatedWithoutMutation(t *testing.T) {
	original := `{"Time":"2026-10-29T12:00:00Z","Action":"folder","Status":"error","Result":"write C:\\Папка\\file: There is not enough space on the disk."}`
	lines := []string{original}
	converted := logLinesForUI(lines)
	var event struct{ Result errorRecord }
	if json.Unmarshal([]byte(converted[0]), &event) != nil || !strings.Contains(event.Result.Message, "Недостаточно свободного места") || !strings.Contains(event.Result.Details, "There is not enough space") {
		t.Fatal("legacy error lost explanation or details", converted)
	}
	if lines[0] != original {
		t.Fatal("original journal mutated")
	}
}
