package main

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"mime"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// These fixtures are invented. No user export or filename map is included.
func mappedAssetFixture(t *testing.T) (*Store, string, map[string][]byte) {
	t.Helper()
	s := newTestStore(t)
	obj := fixture("synthetic-chat", "Документ и картинка", 1700000020)
	question := obj["mapping"].(map[string]any)["question"].(map[string]any)["message"].(map[string]any)
	question["content"] = map[string]any{"parts": []any{"Покажи картинку", map[string]any{"content_type": "image_asset_pointer", "asset_pointer": "sediment://file_picture"}}}
	question["metadata"] = map[string]any{"attachments": []any{map[string]any{"id": "file_document", "name": "Отчёт.pdf"}, map[string]any{"id": "file_missing"}}}
	answer := obj["mapping"].(map[string]any)["answer"].(map[string]any)["message"].(map[string]any)
	answer["content"] = map[string]any{"parts": []any{"Имя Одинаковое.xlsx само по себе не создаёт связь"}}
	raw, _ := json.Marshal([]any{obj})
	names, _ := json.Marshal(map[string]string{
		"file_picture.dat": "Картинка #100%.png", "file_document.dat": "Отчёт.pdf",
		"file_audio.dat": "synthetic-chat/audio/запись.wav", "file_other.dat": "Одинаковое.xlsx",
		"file_duplicate.dat": "Отчёт.pdf", "file_missing.dat": "Отсутствует.pdf",
		"file_path.dat": "../../CON.txt", "../outside.dat": "Нельзя.txt",
	})
	payloads := map[string][]byte{
		"wrapped/conversations-000.json": raw, "wrapped/conversation_asset_file_names.json": names,
		"wrapped/file_picture.dat": []byte("synthetic image bytes"), "wrapped/file_document.dat": []byte("synthetic document"),
		"wrapped/file_audio.dat": []byte("synthetic audio"), "wrapped/file_other.dat": []byte("synthetic unrelated workbook"),
		"wrapped/file_duplicate.dat": []byte("different document with same name"), "wrapped/file_path.dat": []byte("safe basename"),
		"wrapped/unmapped.dat": []byte("unnamed bytes"), "file_picture.dat": []byte("outside map scope"),
	}
	r, err := s.ImportFile(zipFile(t, payloads))
	if err != nil || r.New != 1 {
		t.Fatalf("import %+v %v", r, err)
	}
	return s, r.SourceID, payloads
}

func TestAssetNamesOldCatalogAndSourceAPI(t *testing.T) {
	s, id, payloads := mappedAssetFixture(t)
	catalog := filepath.Join(s.Vault, "catalog.json")
	before, err := os.ReadFile(catalog)
	if err != nil {
		t.Fatal(err)
	}
	reopened, err := openStore(s.Root)
	if err != nil {
		t.Fatal(err)
	}
	entries, report := reopened.namedEntries(reopened.Cat.Sources[id])
	if report.Declared != 7 || report.Resolved != 6 || len(report.Missing) != 1 || len(report.Warnings) != 1 {
		t.Fatalf("%+v", report)
	}
	found := map[string]Entry{}
	for _, entry := range entries {
		found[entry.Path] = entry
		if want, ok := payloads[entry.Path]; ok {
			got, e := os.ReadFile(reopened.objectPath(entry.Hash))
			if e != nil || !bytes.Equal(got, want) {
				t.Fatal("original bytes changed", entry.Path, e)
			}
		}
	}
	if found["wrapped/file_picture.dat"].OriginalName != "Картинка #100%.png" || found["file_picture.dat"].OriginalName != "" || found["wrapped/unmapped.dat"].OriginalName != "" {
		t.Fatal("name resolution escaped scope or omitted unknown file")
	}
	for _, entry := range reopened.Cat.Sources[id].Entries {
		if entry.OriginalName != "" {
			t.Fatal("catalog entry mutated")
		}
	}
	a := &App{store: reopened, token: "synthetic-asset-token"}
	req := httptest.NewRequest("GET", "http://127.0.0.1:1234/api/source?id="+id, nil)
	req.Header.Set("X-BS-Token", a.token)
	w := httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	var response struct {
		Entries    []Entry
		AssetNames AssetNameReport
	}
	if err = json.Unmarshal(w.Body.Bytes(), &response); w.Code != 200 || err != nil || response.AssetNames.Resolved != 6 {
		t.Fatal("source API", w.Code, err)
	}
	for i, entry := range response.Entries {
		if entry.Path != "wrapped/file_document.dat" {
			continue
		}
		req = httptest.NewRequest("GET", fmt.Sprintf("http://127.0.0.1:1234/api/file?source=%s&index=%d", id, i), nil)
		req.Header.Set("X-BS-Token", a.token)
		w = httptest.NewRecorder()
		a.handler().ServeHTTP(w, req)
		_, params, e := mime.ParseMediaType(w.Header().Get("Content-Disposition"))
		if w.Code != 200 || e != nil || params["filename"] != "Отчёт.pdf" || !bytes.Equal(w.Body.Bytes(), payloads[entry.Path]) {
			t.Fatal("named download changed data", w.Code, params, e)
		}
	}
	after, err := os.ReadFile(catalog)
	if err != nil || !bytes.Equal(before, after) {
		t.Fatal("reading aliases rewrote old catalog", err)
	}
	if checked := s.Verify(); len(checked.Errors) != 0 {
		t.Fatal(checked.Errors)
	}
}

func TestExplicitChatAttachmentsAndMissingFiles(t *testing.T) {
	s, _, _ := mappedAssetFixture(t)
	a := &App{store: s, token: "synthetic-chat-token"}
	req := httptest.NewRequest("GET", "http://127.0.0.1:1234/api/conversation?id=synthetic-chat", nil)
	req.Header.Set("X-BS-Token", a.token)
	w := httptest.NewRecorder()
	a.handler().ServeHTTP(w, req)
	var response struct {
		Messages    []Message
		Attachments []Attachment
	}
	if err := json.Unmarshal(w.Body.Bytes(), &response); w.Code != 200 || err != nil {
		t.Fatal(w.Code, err)
	}
	// Two byte variants of file_picture from separate paths remain available;
	// audio is linked to the chat by its explicit original conversation path.
	if len(response.Attachments) != 4 {
		t.Fatalf("chat assets: %+v", response.Attachments)
	}
	for _, item := range response.Attachments {
		if strings.Contains(item.SourcePath, "other") || strings.Contains(item.SourcePath, "missing") || strings.Contains(item.SourcePath, "duplicate") {
			t.Fatal("guessed attachment", item)
		}
	}
	for _, message := range response.Messages {
		if message.ID == "question" && len(message.Attachments) != 3 {
			t.Fatalf("message assets %+v", message)
		}
		if message.ID == "answer" && len(message.Attachments) != 0 {
			t.Fatal("matched filename without explicit ID")
		}
	}
	// Also support the collector's flat message list and avoid token prefixes.
	obj := map[string]any{"messages": []any{map[string]any{"role": "user", "content": "file_document-extra is not file_document"}}}
	msgs, _ := messagesWithAssets(obj, "unrelated", s.indexAssets())
	if len(msgs) != 1 || len(msgs[0].Attachments) != 1 {
		t.Fatal("exact token matching", msgs)
	}
	obj["messages"] = []any{map[string]any{"role": "user", "content": "file_document-extra"}}
	msgs, assets := messagesWithAssets(obj, "unrelated", s.indexAssets())
	if len(msgs[0].Attachments) != 0 || len(assets) != 0 {
		t.Fatal("prefix or filename guessing")
	}
}

func TestMappedMigrationNamesManifestAndAttachments(t *testing.T) {
	s, _, payloads := mappedAssetFixture(t)
	out, err := s.MigrationTo(t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	z, err := zip.OpenReader(out.(map[string]any)["Path"].(string))
	if err != nil {
		t.Fatal(err)
	}
	defer z.Close()
	files := map[string][]byte{}
	for _, entry := range z.File {
		if !safeArchivePath(entry.Name) {
			t.Fatal("unsafe exported path", entry.Name)
		}
		r, e := entry.Open()
		if e != nil {
			t.Fatal(e)
		}
		data, e := io.ReadAll(r)
		r.Close()
		if e != nil {
			t.Fatal(e)
		}
		files[entry.Name] = data
	}
	var manifest struct {
		Schema        int
		Files         []Attachment
		AssetMappings []AssetNameReport
	}
	if err = json.Unmarshal(files["FILES_MANIFEST.json"], &manifest); err != nil || manifest.Schema != 1 || len(manifest.AssetMappings) != 1 || manifest.AssetMappings[0].Resolved != 6 {
		t.Fatal("invalid mapping manifest", err)
	}
	docCount := 0
	for _, entry := range manifest.Files {
		if sum(files[entry.Path]) != entry.Hash || int64(len(files[entry.Path])) != entry.Size {
			t.Fatal("hash mismatch", entry)
		}
		if want, ok := payloads[entry.SourcePath]; ok && !bytes.Equal(files[entry.Path], want) {
			t.Fatal("asset bytes changed", entry)
		}
		if entry.Name == "Отчёт.pdf" {
			docCount++
		}
		if strings.HasSuffix(entry.SourcePath, "file_path.dat") && !strings.HasSuffix(entry.Path, "/_CON.txt") {
			t.Fatal("unsafe basename not sanitized", entry)
		}
	}
	if docCount != 2 {
		t.Fatal("duplicate friendly names overwritten", docCount)
	}
	html := string(files["index.html"])
	start := strings.Index(html, `<script id="archive-data" type="application/json">`)
	start += len(`<script id="archive-data" type="application/json">`)
	end := strings.Index(html[start:], "</script>")
	var archive struct {
		Chats []struct {
			Messages    []Message
			Attachments []Attachment
		}
	}
	if end < 0 || json.Unmarshal([]byte(html[start:start+end]), &archive) != nil || len(archive.Chats) != 1 || len(archive.Chats[0].Attachments) != 4 {
		t.Fatal("offline chat lost attachment links")
	}
	if checked := s.Verify(); len(checked.Errors) != 0 {
		t.Fatal(checked.Errors)
	}
}

func TestPortableAssetNameKeepsExtension(t *testing.T) {
	for _, name := range []string{strings.Repeat("я", 200) + ".xlsx", strings.Repeat("界", 160) + ".png"} {
		got := portableName(name)
		if len(got) > 200 || len([]rune(got)) > 150 || filepath.Ext(got) != filepath.Ext(name) {
			t.Fatal("unusable long name", got)
		}
	}
}
