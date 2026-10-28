package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fixture(id, text string, updated int) map[string]any {
	return map[string]any{
		"id": id, "title": "Тест резервирования", "create_time": 1700000000, "update_time": updated, "current_node": "answer",
		"mapping": map[string]any{
			"root":       map[string]any{"id": "root", "parent": nil, "message": nil},
			"question":   map[string]any{"parent": "root", "message": map[string]any{"author": map[string]any{"role": "user"}, "create_time": 1700000001, "content": map[string]any{"parts": []any{"Что сохранить?"}}}},
			"answer":     map[string]any{"parent": "question", "message": map[string]any{"author": map[string]any{"role": "assistant"}, "create_time": 1700000002, "content": map[string]any{"parts": []any{text}}}},
			"old-answer": map[string]any{"parent": "question", "message": map[string]any{"author": map[string]any{"role": "assistant"}, "create_time": 1700000002, "content": map[string]any{"parts": []any{"Другая ветвь"}}}},
		},
	}
}
func newTestStore(t *testing.T) *Store {
	t.Helper()
	s, e := openStore(t.TempDir())
	if e != nil {
		t.Fatal(e)
	}
	return s
}
func jsonFile(t *testing.T, v any, name string) string {
	t.Helper()
	b, e := json.Marshal(v)
	if e != nil {
		t.Fatal(e)
	}
	p := filepath.Join(t.TempDir(), name)
	if e = os.WriteFile(p, b, 0600); e != nil {
		t.Fatal(e)
	}
	return p
}
func zipFile(t *testing.T, files map[string][]byte) string {
	t.Helper()
	var b bytes.Buffer
	z := zip.NewWriter(&b)
	for name, data := range files {
		w, e := z.Create(name)
		if e != nil {
			t.Fatal(e)
		}
		if _, e = w.Write(data); e != nil {
			t.Fatal(e)
		}
	}
	if e := z.Close(); e != nil {
		t.Fatal(e)
	}
	p := filepath.Join(t.TempDir(), "export.zip")
	if e := os.WriteFile(p, b.Bytes(), 0600); e != nil {
		t.Fatal(e)
	}
	return p
}
func TestImportRevisionsBranchesAndDedup(t *testing.T) {
	s := newTestStore(t)
	p := jsonFile(t, []any{fixture("chat1", "Важная мысль", 1700000010)}, "conversations.json")
	r, e := s.ImportFile(p)
	if e != nil || r.New != 1 {
		t.Fatalf("%+v %v", r, e)
	}
	c := s.Cat.Conversations["chat1"]
	if c.Messages != 3 || len(c.Revisions) != 1 {
		t.Fatalf("%+v", c)
	}
	b, _ := os.ReadFile(filepath.Join(s.Vault, c.Revisions[0].Markdown))
	if !bytes.Contains(b, []byte("Другая ветвь")) {
		t.Fatal("branch dropped")
	}
	r, e = s.ImportFile(p)
	if e != nil || !r.Duplicate {
		t.Fatalf("%+v %v", r, e)
	}
	alias := filepath.Join(t.TempDir(), "renamed.json")
	raw, _ := os.ReadFile(p)
	_ = os.WriteFile(alias, raw, 0600)
	r, e = s.ImportFile(alias)
	if e != nil || !r.Duplicate || len(s.Cat.Sources[r.SourceID].Aliases) != 1 {
		t.Fatal("alias was lost")
	}
	p2 := jsonFile(t, []any{fixture("chat1", "Обновлённая мысль", 1700000020)}, "conversations-1.json")
	r, e = s.ImportFile(p2)
	if e != nil || r.Updated != 1 || len(s.Cat.Conversations["chat1"].Revisions) != 2 {
		t.Fatalf("%+v %v", r, e)
	}
	if v := s.Verify(); len(v.Errors) > 0 {
		t.Fatal(v.Errors)
	}
	latest := s.Cat.Conversations["chat1"].Latest
	older := jsonFile(t, []any{fixture("chat1", "Ещё более ранний вариант", 1690000000)}, "older.json")
	if _, e = s.ImportFile(older); e != nil {
		t.Fatal(e)
	}
	if s.Cat.Conversations["chat1"].Latest != latest {
		t.Fatal("older export replaced current revision")
	}
	reopened, e := openStore(s.Root)
	if e != nil || len(reopened.Cat.Conversations["chat1"].Revisions) != 3 {
		t.Fatal(e)
	}
}
func TestMultipartAndCollectorZIP(t *testing.T) {
	s := newTestStore(t)
	one, _ := json.Marshal([]any{fixture("one", "Первый", 1700000001)})
	two, _ := json.Marshal(fixture("two", "Второй", 1700000002))
	file := []byte("original attachment")
	manifest, _ := json.Marshal(map[string]any{"files": []any{map[string]any{"name": "files/document.txt", "sha256": sum(file)}}})
	p := zipFile(t, map[string][]byte{"conversations-000.json": one, "conversations/second/raw.json": two, "files/document.txt": file, "manifest.json": manifest})
	r, e := s.ImportFile(p)
	if e != nil || r.New != 2 || len(r.Warnings) != 0 {
		t.Fatalf("%+v %v", r, e)
	}
	entries := s.Cat.Sources[r.SourceID].Entries
	if len(entries) != 5 {
		t.Fatal(entries)
	}
	got, e := os.ReadFile(s.objectPath(sum(file)))
	if e != nil || !bytes.Equal(got, file) {
		t.Fatal(e)
	}
}
func TestUnsafeAndCorruptSourcesPreserved(t *testing.T) {
	s := newTestStore(t)
	p := zipFile(t, map[string][]byte{"../outside.txt": []byte("unsafe")})
	r, e := s.ImportFile(p)
	if e != nil || len(r.Warnings) == 0 {
		t.Fatalf("%+v %v", r, e)
	}
	src := s.Cat.Sources[r.SourceID]
	if len(src.Entries) != 1 || src.Status != "partial" {
		t.Fatal(src)
	}
	manifest, _ := json.Marshal(map[string]any{"files": []any{map[string]any{"name": "file.txt", "sha256": strings.Repeat("a", 64)}}})
	r, e = s.ImportFile(zipFile(t, map[string][]byte{"file.txt": []byte("changed"), "manifest.json": manifest}))
	if e != nil || len(r.Warnings) == 0 {
		t.Fatalf("%+v %v", r, e)
	}
	bad := filepath.Join(t.TempDir(), "bad.zip")
	_ = os.WriteFile(bad, []byte("not a zip"), 0600)
	r, e = s.ImportFile(bad)
	if e != nil || len(r.Warnings) == 0 {
		t.Fatalf("%+v %v", r, e)
	}
}
func TestMemoryNotesAndTamper(t *testing.T) {
	s := newTestStore(t)
	r, e := s.ImportFile(jsonFile(t, map[string]any{"memories": []any{map[string]any{"text": "Вымышленная память"}}}, "memories.json"))
	if e != nil || s.Cat.Sources[r.SourceID].Kind != "memory" || len(s.Cat.Notes) != 1 {
		t.Fatal(e)
	}
	if e = s.AddNote("instructions", "Проверяй источники."); e != nil {
		t.Fatal(e)
	}
	if e = s.AddNote("instructions", "Проверяй источники."); e != nil || len(s.Cat.Notes) != 2 {
		t.Fatal("duplicate note")
	}
	if v := s.Verify(); len(v.Errors) > 0 {
		t.Fatal(v.Errors)
	}
	n := s.Cat.Notes[1]
	_ = os.WriteFile(filepath.Join(s.Vault, n.Path), []byte("изменено"), 0600)
	if v := s.Verify(); len(v.Errors) == 0 {
		t.Fatal("tamper missed")
	}
}
func TestFolderSnapshot(t *testing.T) {
	s := newTestStore(t)
	dir := t.TempDir()
	_ = os.Mkdir(filepath.Join(dir, "sub"), 0700)
	_ = os.WriteFile(filepath.Join(dir, "sub", "программа.txt"), []byte("v1"), 0600)
	r, e := s.ImportFolder(dir)
	if e != nil || r.Files != 1 {
		t.Fatalf("%+v %v", r, e)
	}
	r, e = s.ImportFolder(dir)
	if e != nil || !r.Duplicate {
		t.Fatal("folder duplication")
	}
	_ = os.WriteFile(filepath.Join(dir, "sub", "программа.txt"), []byte("v2"), 0600)
	r, e = s.ImportFolder(dir)
	if e != nil || r.Duplicate || len(s.Cat.Sources) != 2 {
		t.Fatal("folder revision lost")
	}
	if _, e = s.ImportFolder(s.Root); e == nil {
		t.Fatal("recursive import allowed")
	}
}
func TestMigrationAndHTMLSafety(t *testing.T) {
	s := newTestStore(t)
	obj := fixture("unsafe", "</script><img src=x onerror=alert(1)>", 1700000010)
	obj["title"] = "<script>bad()</script>"
	if _, e := s.ImportFile(jsonFile(t, obj, "raw.json")); e != nil {
		t.Fatal(e)
	}
	out, e := s.Migration()
	if e != nil {
		t.Fatal(e)
	}
	name := out.(map[string]any)["Name"].(string)
	z, e := zip.OpenReader(filepath.Join(s.Root, "Outbox", name))
	if e != nil {
		t.Fatal(e)
	}
	defer z.Close()
	found := false
	for _, f := range z.File {
		if !safeArchivePath(f.Name) {
			t.Fatal("unsafe output")
		}
		if f.Name == "index.html" {
			rc, _ := f.Open()
			b, _ := io.ReadAll(rc)
			rc.Close()
			found = true
			if bytes.Contains(b, []byte("</script><img")) || bytes.Contains(b, []byte("<script>bad()")) {
				t.Fatal("unescaped embedded data")
			}
		}
	}
	if !found {
		t.Fatal("offline viewer missing")
	}
}
func TestCatalogValidation(t *testing.T) {
	s := newTestStore(t)
	s.Cat.Sources["short"] = Source{ID: "short"}
	if s.validate() == nil {
		t.Fatal("invalid hash accepted")
	}
}
func TestHTTPBoundaryAndSearch(t *testing.T) {
	s := newTestStore(t)
	_, _ = s.ImportFile(jsonFile(t, fixture("search", "Найдём слово космодром", 1700000001), "raw.json"))
	a := &App{store: s, token: "secret-test", cfg: Config{}, seen: map[string]string{}}
	for _, test := range []struct {
		token, origin string
		want          int
	}{{"", "", 403}, {"secret-test", "http://evil.example", 403}, {"secret-test", "http://127.0.0.1:12345", 200}} {
		req := httptest.NewRequest("GET", "http://127.0.0.1:12345/api/state", nil)
		req.Header.Set("X-BS-Token", test.token)
		req.Header.Set("Origin", test.origin)
		w := httptest.NewRecorder()
		a.handler().ServeHTTP(w, req)
		if w.Code != test.want {
			t.Fatal(w.Code, w.Body.String())
		}
	}
	req := httptest.NewRequest("GET", "http://127.0.0.1:12345/api/search?q=космодром", nil)
	req.Header.Set("X-BS-Token", "secret-test")
	w := httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	if w.Code != http.StatusOK || !strings.Contains(w.Body.String(), "search") {
		t.Fatal(w.Body.String())
	}
}
func TestPortableNames(t *testing.T) {
	for _, n := range []string{"CON.txt", "LPT1", "a:b.txt", "../тест?.txt"} {
		p := portableName(n)
		if strings.ContainsAny(p, ":?<>|/\\") || strings.EqualFold(p, "CON.txt") || strings.EqualFold(p, "LPT1") {
			t.Fatal(p)
		}
	}
}
func TestSettlingInbox(t *testing.T) {
	s := newTestStore(t)
	a := &App{store: s, seen: map[string]string{}}
	p := filepath.Join(s.Root, "Inbox", "raw.json")
	b, _ := json.Marshal(fixture("inbox", "тест", 1700000001))
	_ = os.WriteFile(p, b, 0600)
	if a.pendingInbox() {
		t.Fatal("incomplete upload accepted")
	}
	old := time.Now().Add(-20 * time.Second)
	_ = os.Chtimes(p, old, old)
	if !a.pendingInbox() {
		t.Fatal("stable upload missed")
	}
	if _, e := a.scan(); e != nil {
		t.Fatal(e)
	}
	if a.pendingInbox() {
		t.Fatal("unchanged source rescanned")
	}
}

func TestScheduledInvocationForwarding(t *testing.T) {
	s := newTestStore(t)
	a := &App{store: s, token: strings.Repeat("a", 48), cfg: Config{WatchEnabled: true}, seen: map[string]string{}}
	server := httptest.NewServer(a.handler())
	defer server.Close()
	if e := os.WriteFile(filepath.Join(s.Root, "server-address.txt"), []byte(server.URL), 0600); e != nil {
		t.Fatal(e)
	}
	b, _ := json.Marshal(fixture("scheduled", "Запуск по расписанию", 1700000001))
	p := filepath.Join(s.Root, "Inbox", "scheduled.json")
	if e := os.WriteFile(p, b, 0600); e != nil {
		t.Fatal(e)
	}
	old := time.Now().Add(-20 * time.Second)
	_ = os.Chtimes(p, old, old)
	if e := forwardRunOnce(s.Root); e != nil {
		t.Fatal(e)
	}
	for i := 0; i < 100; i++ {
		a.mu.Lock()
		job := a.job
		a.mu.Unlock()
		if !job.Running && job.Action == "run-once" {
			if job.Error != "" {
				t.Fatal(job.Error)
			}
			s.mu.RLock()
			count := len(s.Cat.Conversations)
			s.mu.RUnlock()
			if count != 1 {
				t.Fatal("scheduled import missed")
			}
			return
		}
		time.Sleep(10 * time.Millisecond)
	}
	t.Fatal("scheduled forwarding timed out")
}
func TestResticRoundTrip(t *testing.T) {
	bin := os.Getenv("BS_TEST_RESTIC")
	if bin == "" {
		t.Skip("set BS_TEST_RESTIC for real encryption/restore test")
	}
	h, _, e := hashFile(bin)
	if e != nil {
		t.Fatal(e)
	}
	engine := &Engine{Binary: bin, ExpectedHash: h}
	s := newTestStore(t)
	_, e = s.ImportFile(jsonFile(t, fixture("roundtrip", "Сохранить это навсегда", 1700000001), "conversations.json"))
	if e != nil {
		t.Fatal(e)
	}
	if e = s.AddNote("memory", "Вымышленный проверочный факт"); e != nil {
		t.Fatal(e)
	}
	repo := filepath.Join(t.TempDir(), "repository")
	pass := "Test-only password 2026!"
	if _, e = engine.run(s.Root, repo, pass, "init"); e != nil {
		t.Fatal(e)
	}
	id, e := engine.backup(s, repo, pass)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = engine.run(s.Root, repo, "wrong password", "check"); e == nil {
		t.Fatal("wrong password accepted")
	}
	snapshots, e := engine.snapshots(s.Root, repo, pass)
	if e != nil || len(snapshots) != 1 {
		t.Fatalf("%+v %v", snapshots, e)
	}
	if _, e = engine.run(s.Root, repo, pass, "check", "--read-data"); e != nil {
		t.Fatal(e)
	}
	target := filepath.Join(t.TempDir(), "restored")
	result, e := engine.restore(s, repo, pass, id, target)
	if e != nil || len(result.Errors) > 0 || result.Checked == 0 {
		t.Fatalf("%+v %v", result, e)
	}
	if _, e = engine.restore(s, repo, pass, id, target); e == nil {
		t.Fatal("nonempty restore target accepted")
	}
	if _, e = engine.restore(s, repo, pass, id, s.Root); e == nil {
		t.Fatal("in-place restore allowed")
	}
	var pack string
	_ = filepath.WalkDir(filepath.Join(repo, "data"), func(p string, d os.DirEntry, e error) error {
		if e == nil && !d.IsDir() && pack == "" {
			pack = p
		}
		return nil
	})
	if pack == "" {
		t.Fatal("pack not found")
	}
	b, _ := os.ReadFile(pack)
	b[len(b)/2] ^= 0xff
	if e = os.Chmod(pack, 0600); e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(pack, b, 0600); e != nil {
		t.Fatal(e)
	}
	if _, e = engine.run(s.Root, repo, pass, "check", "--read-data"); e == nil {
		t.Fatal("encrypted corruption missed")
	}
}
