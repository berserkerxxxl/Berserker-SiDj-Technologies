package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"io"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func fileLinkFixture(t *testing.T) (*Store, string, int, []byte) {
	t.Helper()
	s, _, _ := mappedAssetFixture(t)
	payload := []byte("Invented presentation bytes for archive tests; no user file.")
	p := filepath.Join(t.TempDir(), "Слайд 4x3.pptx")
	if err := os.WriteFile(p, payload, 0600); err != nil {
		t.Fatal(err)
	}
	r, err := s.ImportFile(p)
	if err != nil {
		t.Fatal(err)
	}
	for i, entry := range s.Cat.Sources[r.SourceID].Entries {
		if entry.Hash == sum(payload) {
			return s, r.SourceID, i, payload
		}
	}
	t.Fatal("presentation missing from source")
	return nil, "", 0, nil
}

func TestManualFileLinkPersistsAndMigrates(t *testing.T) {
	s, sourceID, index, payload := fileLinkFixture(t)
	c := s.Cat.Conversations["synthetic-chat"]
	rev := c.Revisions[0]
	jsonPath := filepath.Join(s.Vault, filepath.FromSlash(rev.JSON))
	mdPath := filepath.Join(s.Vault, filepath.FromSlash(rev.Markdown))
	beforeJSON, _ := os.ReadFile(jsonPath)
	beforeMD, _ := os.ReadFile(mdPath)
	if changed, err := s.SetFileLink(c.ID, sourceID, index, false); err != nil || !changed {
		t.Fatal(changed, err)
	}
	beforeCatalog, _ := os.ReadFile(filepath.Join(s.Vault, "catalog.json"))
	if changed, err := s.SetFileLink(c.ID, sourceID, index, false); err != nil || changed {
		t.Fatal("duplicate link", changed, err)
	}
	afterCatalog, _ := os.ReadFile(filepath.Join(s.Vault, "catalog.json"))
	if !bytes.Equal(beforeCatalog, afterCatalog) {
		t.Fatal("duplicate link rewrote catalog")
	}
	s, err := openStore(s.Root)
	if err != nil || len(s.Cat.FileLinks) != 1 {
		t.Fatal("reopen", err)
	}
	choices, total, err := s.FileChoices(c.ID, ".PPTX")
	if err != nil || total != 1 || len(choices) != 1 || !choices[0].Linked || !choices[0].Manual {
		t.Fatal(choices, total, err)
	}
	migrated, err := s.MigrationTo(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	z, err := zip.OpenReader(migrated.(map[string]any)["Path"].(string))
	if err != nil {
		t.Fatal(err)
	}
	defer z.Close()
	files := map[string][]byte{}
	for _, f := range z.File {
		r, err := f.Open()
		if err != nil {
			t.Fatal(err)
		}
		files[f.Name], err = io.ReadAll(r)
		r.Close()
		if err != nil {
			t.Fatal(err)
		}
	}
	var manifest struct{ FileLinks []FileLink }
	if err := json.Unmarshal(files["FILES_MANIFEST.json"], &manifest); err != nil || len(manifest.FileLinks) != 1 {
		t.Fatal("migration link manifest", err)
	}
	path := choices[0].Path
	if !bytes.Equal(files[path], payload) {
		t.Fatal("presentation bytes changed")
	}
	html := string(files["index.html"])
	marker := `<script id="archive-data" type="application/json">`
	data := strings.Split(strings.Split(html, marker)[1], "</script>")[0]
	var offline struct {
		Chats []struct {
			ID          string
			Attachments []Attachment
		}
	}
	if err := json.Unmarshal([]byte(data), &offline); err != nil {
		t.Fatal(err)
	}
	found := false
	for _, chat := range offline.Chats {
		for _, item := range chat.Attachments {
			if chat.ID == c.ID && item.Path == path {
				found = true
			}
		}
	}
	if !found {
		t.Fatal("manual attachment missing from offline chat")
	}
	if changed, err := s.SetFileLink(c.ID, sourceID, index, true); err != nil || !changed {
		t.Fatal(changed, err)
	}
	choices, _, err = s.FileChoices(c.ID, ".pptx")
	if err != nil || choices[0].Linked || choices[0].Manual {
		t.Fatal("unlink", choices, err)
	}
	afterJSON, _ := os.ReadFile(jsonPath)
	afterMD, _ := os.ReadFile(mdPath)
	stored, _ := os.ReadFile(s.objectPath(sum(payload)))
	if !bytes.Equal(beforeJSON, afterJSON) || !bytes.Equal(beforeMD, afterMD) || !bytes.Equal(stored, payload) {
		t.Fatal("link/unlink modified original data")
	}
	if len(s.Verify().Errors) != 0 {
		t.Fatal("archive failed verification after unlink")
	}
}

func TestManualFileLinkValidationAndWriteFailure(t *testing.T) {
	s, sourceID, index, _ := fileLinkFixture(t)
	for _, target := range []struct {
		conversation, source string
		index                int
	}{{"missing", sourceID, index}, {"synthetic-chat", "missing", index}, {"synthetic-chat", sourceID, -1}, {"synthetic-chat", sourceID, 100000}} {
		if _, err := s.SetFileLink(target.conversation, target.source, target.index, false); err == nil {
			t.Fatal("accepted invalid target", target)
		}
	}
	if len(s.Cat.FileLinks) != 0 {
		t.Fatal("invalid operation changed links")
	}
	catalog := filepath.Join(s.Vault, "catalog.json")
	backup := catalog + ".test-backup"
	if err := os.Rename(catalog, backup); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(catalog, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(catalog, "block-replacement"), []byte("test"), 0600); err != nil {
		t.Fatal(err)
	}
	changed, err := s.SetFileLink("synthetic-chat", sourceID, index, false)
	if err == nil || changed || len(s.Cat.FileLinks) != 0 {
		t.Fatal("failed write left an in-memory attachment", changed, err)
	}
	if err := os.RemoveAll(catalog); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(backup, catalog); err != nil {
		t.Fatal(err)
	}
	if _, err := s.SetFileLink("synthetic-chat", sourceID, index, false); err != nil {
		t.Fatal(err)
	}
	s.Cat.FileLinks[0].Hash = strings.Repeat("0", 64)
	if err := s.validate(); err == nil || len(s.Verify().Errors) == 0 {
		t.Fatal("damaged link was accepted")
	}
	if err := s.save(); err != nil {
		t.Fatal(err)
	}
	if _, err := openStore(s.Root); err == nil {
		t.Fatal("reopened a corrupted file link")
	}
}

func TestFileChoiceAndLinkHTTP(t *testing.T) {
	s, sourceID, index, _ := fileLinkFixture(t)
	a := &App{store: s, token: "synthetic-file-link-token"}
	handler := a.handler()
	get := func(query, token string) *httptest.ResponseRecorder {
		r := httptest.NewRequest("GET", "http://127.0.0.1:1234/api/files?"+query, nil)
		r.Header.Set("X-BS-Token", token)
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		return w
	}
	if w := get("conversation=synthetic-chat", ""); w.Code != 403 {
		t.Fatal("file picker accepted unauthenticated request", w.Code)
	}
	w := get("conversation=synthetic-chat&q=.pptx", a.token)
	var options struct {
		Files []FileChoice
		Total int
	}
	if err := json.Unmarshal(w.Body.Bytes(), &options); w.Code != 200 || err != nil || options.Total != 1 || options.Files[0].Linked {
		t.Fatal(w.Code, options, err)
	}
	request := ActionRequest{Action: "file-link", ConversationID: "synthetic-chat", SourceID: sourceID, FileIndex: &index}
	for _, remove := range []bool{false, true} {
		request.Remove = remove
		body, _ := json.Marshal(request)
		r := httptest.NewRequest("POST", "http://127.0.0.1:1234/api/action", bytes.NewReader(body))
		r.Header.Set("X-BS-Token", a.token)
		w = httptest.NewRecorder()
		handler.ServeHTTP(w, r)
		if w.Code != 200 {
			t.Fatal(w.Code, w.Body.String())
		}
		deadline := time.Now().Add(5 * time.Second)
		for {
			a.mu.Lock()
			job := a.job
			a.mu.Unlock()
			if !job.Running {
				if job.Error != "" || job.Action != "file-link" {
					t.Fatal(job)
				}
				break
			}
			if time.Now().After(deadline) {
				t.Fatal("file-link job did not finish")
			}
			time.Sleep(time.Millisecond)
		}
		w = get("conversation=synthetic-chat&q=.pptx", a.token)
		if err := json.Unmarshal(w.Body.Bytes(), &options); err != nil || options.Files[0].Linked == remove || options.Files[0].Manual == remove {
			t.Fatal(options, err)
		}
	}
}
