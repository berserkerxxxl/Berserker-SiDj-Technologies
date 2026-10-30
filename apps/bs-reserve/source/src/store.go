package main

import (
	"archive/zip"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"
)

const Version = "0.1.0-alpha.9"
const Build = "20261030.4"
const maxSource = int64(2 << 30)
const maxJSON = int64(256 << 20)
const maxExpanded = uint64(8 << 30)
const maxEntries = 100000

type Entry struct {
	Path, Hash   string
	Size         int64
	OriginalName string `json:",omitempty"`
}
type Source struct {
	ID, Name, Kind, ImportedAt, Status string
	Size                               int64
	Entries                            []Entry
	ConversationIDs, Warnings          []string
	Aliases                            []string
}
type Revision struct {
	Hash, JSON, Markdown, MarkdownHash, ImportedAt string
}
type Conversation struct {
	ID, Title, Latest, SourceID string
	Created, Updated            float64
	Messages                    int
	Revisions                   []Revision
}
type Note struct {
	ID, Kind, Path, Hash, CreatedAt string
}
type Catalog struct {
	Schema        int
	Version       string
	Sources       map[string]Source
	Conversations map[string]Conversation
	Notes         []Note
	FileLinks     []FileLink `json:",omitempty"`
}
type ImportResult struct {
	SourceID            string
	New, Updated, Files int
	Duplicate           bool
	Warnings            []string
}
type Store struct {
	mu          sync.RWMutex
	Root, Vault string
	Cat         Catalog
}

func now() string { return time.Now().UTC().Format(time.RFC3339) }
func sum(b []byte) string {
	v := sha256.Sum256(b)
	return hex.EncodeToString(v[:])
}
func hashFile(p string) (string, int64, error) {
	f, err := os.Open(p)
	if err != nil {
		return "", 0, err
	}
	defer f.Close()
	h := sha256.New()
	n, err := io.Copy(h, f)
	return hex.EncodeToString(h.Sum(nil)), n, err
}
func atomicWrite(p string, b []byte) error {
	if err := os.MkdirAll(filepath.Dir(p), 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(p), ".reserve-write-*")
	if err != nil {
		return err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	if err = f.Chmod(0600); err == nil {
		_, err = f.Write(b)
	}
	if err == nil {
		err = f.Sync()
	}
	closeErr := f.Close()
	if err != nil {
		return err
	}
	if closeErr != nil {
		return closeErr
	}
	return os.Rename(tmp, p)
}
func writeJSON(p string, v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	return atomicWrite(p, append(b, '\n'))
}
func openStore(root string) (*Store, error) {
	root, err := filepath.Abs(root)
	if err != nil {
		return nil, err
	}
	s := &Store{Root: root, Vault: filepath.Join(root, "Vault")}
	for _, d := range []string{"Vault/objects", "Vault/conversations", "Vault/knowledge", "Inbox", "Outbox", "config", "logs"} {
		if err := os.MkdirAll(filepath.Join(root, filepath.FromSlash(d)), 0700); err != nil {
			return nil, err
		}
	}
	s.Cat = Catalog{Schema: 1, Version: Version, Sources: map[string]Source{}, Conversations: map[string]Conversation{}}
	b, err := os.ReadFile(filepath.Join(s.Vault, "catalog.json"))
	if err == nil {
		if err = json.Unmarshal(b, &s.Cat); err != nil {
			return nil, fmt.Errorf("каталог повреждён; сохранён catalog.previous.json: %w", err)
		}
		if s.Cat.Schema != 1 || s.Cat.Sources == nil || s.Cat.Conversations == nil {
			return nil, errors.New("неподдерживаемая схема каталога")
		}
		if err = s.validate(); err != nil {
			return nil, err
		}
	} else if !os.IsNotExist(err) {
		return nil, err
	}
	if err = atomicWrite(filepath.Join(s.Vault, "README_RESTORE_RU.txt"), []byte(recoveryText)); err != nil {
		return nil, err
	}
	if err = s.save(); err != nil {
		return nil, err
	}
	return s, nil
}
func (s *Store) save() error {
	p := filepath.Join(s.Vault, "catalog.json")
	if old, err := os.ReadFile(p); err == nil {
		if err = atomicWrite(filepath.Join(s.Vault, "catalog.previous.json"), old); err != nil {
			return err
		}
	}
	return writeJSON(p, s.Cat)
}
func (s *Store) objectPath(h string) string {
	return filepath.Join(s.Vault, "objects", h[:2], h)
}
func (s *Store) put(r io.Reader, limit int64) (Entry, error) {
	f, err := os.CreateTemp(filepath.Join(s.Vault, "objects"), ".incoming-*")
	if err != nil {
		return Entry{}, err
	}
	tmp := f.Name()
	defer os.Remove(tmp)
	h := sha256.New()
	n, err := io.Copy(io.MultiWriter(f, h), io.LimitReader(r, limit+1))
	if err == nil && n > limit {
		err = errors.New("превышен допустимый размер файла")
	}
	if err == nil {
		err = f.Sync()
	}
	ce := f.Close()
	if err != nil {
		return Entry{}, err
	}
	if ce != nil {
		return Entry{}, ce
	}
	key := hex.EncodeToString(h.Sum(nil))
	dest := s.objectPath(key)
	if err = os.MkdirAll(filepath.Dir(dest), 0700); err != nil {
		return Entry{}, err
	}
	if _, err = os.Stat(dest); os.IsNotExist(err) {
		if err = os.Rename(tmp, dest); err != nil {
			return Entry{}, err
		}
	} else if err != nil {
		return Entry{}, err
	} else {
		existing, size, e := hashFile(dest)
		if e != nil || existing != key || size != n {
			return Entry{}, errors.New("повреждён существующий объект; сначала восстановите копию")
		}
	}
	return Entry{Hash: key, Size: n}, nil
}

func safeArchivePath(name string) bool {
	name = strings.ReplaceAll(name, "\\", "/")
	if name == "" || strings.ContainsAny(name, ":\x00") || strings.HasPrefix(name, "/") {
		return false
	}
	for _, p := range strings.Split(name, "/") {
		if p == ".." {
			return false
		}
	}
	return path.IsAbs(name) == false && path.Clean(name) != ".."
}
func (s *Store) ImportFile(file string) (ImportResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var result ImportResult
	f, err := os.Open(file)
	if err != nil {
		return result, err
	}
	info, err := f.Stat()
	if err != nil || !info.Mode().IsRegular() {
		f.Close()
		return result, errors.New("источник должен быть обычным файлом")
	}
	if info.Size() > maxSource {
		f.Close()
		return result, errors.New("источник превышает 2 ГиБ; разделите выгрузку на части")
	}
	raw, err := s.put(f, maxSource)
	f.Close()
	if err != nil {
		return result, err
	}
	result.SourceID = raw.Hash
	if old, ok := s.Cat.Sources[raw.Hash]; ok {
		name := filepath.Base(file)
		if old.Name != name {
			found := false
			for _, alias := range old.Aliases {
				if alias == name {
					found = true
				}
			}
			if !found {
				old.Aliases = append(old.Aliases, name)
				s.Cat.Sources[raw.Hash] = old
				if err = s.save(); err != nil {
					return result, err
				}
			}
		}
		result.Duplicate = true
		return result, nil
	}
	src := Source{ID: raw.Hash, Name: filepath.Base(file), Size: raw.Size, ImportedAt: now(), Kind: "file", Status: "saved"}
	raw.Path = src.Name
	src.Entries = append(src.Entries, raw)
	ext := strings.ToLower(filepath.Ext(file))
	if ext == ".zip" {
		src.Kind = "archive"
		z, ze := zip.OpenReader(s.objectPath(raw.Hash))
		if ze != nil {
			src.Warnings = append(src.Warnings, "ZIP не прочитан: исходник сохранён, содержимое не обработано")
		} else {
			var total uint64
			valid := true
			if len(z.File) > maxEntries {
				valid = false
				src.Warnings = append(src.Warnings, "в ZIP слишком много файлов")
			}
			for _, e := range z.File {
				if !safeArchivePath(e.Name) || e.Mode()&os.ModeSymlink != 0 {
					valid = false
					src.Warnings = append(src.Warnings, "небезопасное имя или символическая ссылка в ZIP")
					break
				}
				if e.UncompressedSize64 > maxExpanded-total {
					valid = false
					src.Warnings = append(src.Warnings, "распакованный объём превышает 8 ГиБ")
					break
				}
				total += e.UncompressedSize64
			}
			if valid {
				for _, e := range z.File {
					if e.FileInfo().IsDir() {
						continue
					}
					rc, re := e.Open()
					if re != nil {
						src.Warnings = append(src.Warnings, "не удалось прочитать файл ZIP")
						continue
					}
					item, pe := s.put(rc, int64(e.UncompressedSize64))
					rc.Close()
					if pe != nil {
						src.Warnings = append(src.Warnings, "ошибка чтения/контрольной суммы файла ZIP")
						continue
					}
					item.Path = strings.ReplaceAll(e.Name, "\\", "/")
					src.Entries = append(src.Entries, item)
				}
				s.checkIncomingManifest(&src)
			}
			z.Close()
		}
	}
	for _, e := range src.Entries {
		if strings.ToLower(path.Ext(e.Path)) != ".json" {
			continue
		}
		if e.Size > maxJSON {
			src.Warnings = append(src.Warnings, "JSON больше 256 МиБ сохранён, но не разобран; используйте части выгрузки")
			continue
		}
		b, re := os.ReadFile(s.objectPath(e.Hash))
		if re != nil {
			src.Warnings = append(src.Warnings, "сохранённый JSON не прочитан")
			continue
		}
		var v any
		dec := json.NewDecoder(bytes.NewReader(b))
		dec.UseNumber()
		if dec.Decode(&v) != nil {
			src.Warnings = append(src.Warnings, "не удалось разобрать JSON: "+safeLabel(e.Path))
			continue
		}
		for _, obj := range extractConversations(v) {
			changed, added, id, ce := s.addConversation(obj, src.ID)
			if ce != nil {
				src.Warnings = append(src.Warnings, "разговор не преобразован: "+ce.Error())
				continue
			}
			src.ConversationIDs = append(src.ConversationIDs, id)
			if added {
				result.New++
			} else if changed {
				result.Updated++
			}
		}
		if obj, ok := v.(map[string]any); ok {
			for _, key := range []string{"memories", "memory_entries"} {
				if _, exists := obj[key]; exists {
					rel := filepath.Join("knowledge", "memory-"+e.Hash+".json")
					if re = atomicWrite(filepath.Join(s.Vault, rel), b); re != nil {
						return result, re
					}
					src.Kind = "memory"
					nid := sum([]byte("memory-export\n" + e.Hash))
					found := false
					for _, n := range s.Cat.Notes {
						if n.ID == nid {
							found = true
						}
					}
					if !found {
						s.Cat.Notes = append(s.Cat.Notes, Note{ID: nid, Kind: "memory", Path: filepath.ToSlash(rel), Hash: sum(b), CreatedAt: now()})
					}
					break
				}
			}
		}
	}
	if len(src.Warnings) > 0 {
		src.Status = "partial"
	}
	s.Cat.Sources[src.ID] = src
	if err := s.save(); err != nil {
		return result, err
	}
	result.Files = len(src.Entries)
	result.Warnings = src.Warnings
	return result, nil
}
func safeLabel(s string) string {
	s = strings.ReplaceAll(strings.ReplaceAll(s, "\r", " "), "\n", " ")
	if len(s) > 160 {
		s = s[:160]
	}
	return s
}
func extractConversations(v any) []map[string]any {
	var out []map[string]any
	switch x := v.(type) {
	case []any:
		for _, item := range x {
			out = append(out, extractConversations(item)...)
		}
	case map[string]any:
		if _, ok := x["mapping"].(map[string]any); ok {
			return []map[string]any{x}
		}
		if _, ok := x["messages"].([]any); ok {
			if x["title"] != nil || x["conversation_id"] != nil {
				return []map[string]any{x}
			}
		}
		for _, key := range []string{"conversations", "conversation", "items", "data"} {
			if item, ok := x[key]; ok {
				out = append(out, extractConversations(item)...)
			}
		}
	}
	return out
}
func (s *Store) checkIncomingManifest(src *Source) {
	byPath := map[string]Entry{}
	for _, e := range src.Entries {
		byPath[e.Path] = e
	}
	for _, e := range src.Entries {
		if path.Base(e.Path) != "manifest.json" || e.Size > maxJSON {
			continue
		}
		b, err := os.ReadFile(s.objectPath(e.Hash))
		if err != nil {
			continue
		}
		var m struct {
			Files []struct{ Name, Path, SHA256 string }
		}
		if json.Unmarshal(b, &m) != nil {
			continue
		}
		for _, expected := range m.Files {
			if expected.SHA256 == "" {
				continue
			}
			name := expected.Name
			if name == "" {
				name = expected.Path
			}
			actual, ok := byPath[path.Join(path.Dir(e.Path), name)]
			if !ok || !strings.EqualFold(actual.Hash, expected.SHA256) {
				src.Warnings = append(src.Warnings, "не совпал SHA-256 входного манифеста: "+safeLabel(name))
			}
		}
	}
}
func str(v any) string {
	if v == nil {
		return ""
	}
	if s, ok := v.(string); ok {
		return s
	}
	return fmt.Sprint(v)
}
func number(v any) float64 {
	switch x := v.(type) {
	case json.Number:
		n, _ := x.Float64()
		return n
	case float64:
		return x
	case string:
		t, err := time.Parse(time.RFC3339, x)
		if err == nil {
			return float64(t.Unix())
		}
	}
	return 0
}

type Message struct {
	ID, Parent, Role, Text string
	Created                float64
	Attachments            []Attachment `json:",omitempty"`
}

func contentText(v any) string {
	switch x := v.(type) {
	case string:
		return x
	case []any:
		var parts []string
		for _, p := range x {
			if t := contentText(p); t != "" {
				parts = append(parts, t)
			}
		}
		return strings.Join(parts, "\n")
	case map[string]any:
		if t := str(x["text"]); t != "" {
			return t
		}
		if p, ok := x["parts"]; ok {
			return contentText(p)
		}
		if t := str(x["asset_pointer"]); t != "" {
			return "[Вложение: " + t + "]"
		}
		if t := str(x["content_type"]); t != "" {
			switch t {
			case "thoughts":
				return "[Служебная запись. Оригинал сохранён в JSON.]"
			case "reasoning_recap":
				return "[Служебная сводка. Оригинал сохранён в JSON.]"
			default:
				return "[Этот формат сообщения пока не отображается. Оригинал сохранён в JSON.]"
			}
		}
	}
	return ""
}
func messages(obj map[string]any) []Message {
	out := []Message{}
	if mapping, ok := obj["mapping"].(map[string]any); ok {
		for id, raw := range mapping {
			node, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			m, ok := node["message"].(map[string]any)
			if !ok {
				continue
			}
			role := ""
			if a, ok := m["author"].(map[string]any); ok {
				role = str(a["role"])
			}
			out = append(out, Message{ID: id, Parent: str(node["parent"]), Role: role, Text: contentText(m["content"]), Created: number(m["create_time"])})
		}
	} else if list, ok := obj["messages"].([]any); ok {
		for i, raw := range list {
			m, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			role := str(m["role"])
			out = append(out, Message{ID: fmt.Sprint(i), Role: role, Text: contentText(m["content"]), Created: number(m["created_at"])})
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].Created == out[j].Created {
			return out[i].ID < out[j].ID
		}
		return out[i].Created < out[j].Created
	})
	return out
}
func (s *Store) addConversation(obj map[string]any, sourceID string) (bool, bool, string, error) {
	canonical, err := json.MarshalIndent(obj, "", "  ")
	if err != nil {
		return false, false, "", err
	}
	id := str(obj["conversation_id"])
	if id == "" {
		id = str(obj["id"])
	}
	if id == "" {
		id = "derived-" + sum(canonical)
	}
	h := sum(canonical)
	conv, exists := s.Cat.Conversations[id]
	for _, r := range conv.Revisions {
		if r.Hash == h {
			return false, false, id, nil
		}
	}
	folder := filepath.Join("conversations", sum([]byte(id)))
	j := filepath.Join(folder, h+".json")
	md := filepath.Join(folder, h+".md")
	if err = atomicWrite(filepath.Join(s.Vault, j), canonical); err != nil {
		return false, false, id, err
	}
	msgs := messages(obj)
	title := str(obj["title"])
	if title == "" {
		title = "Без названия"
	}
	var text strings.Builder
	fmt.Fprintf(&text, "# %s\n\nID: %s\n\nВсе доступные узлы разговора; ветви сохранены в JSON.\n", title, id)
	for _, m := range msgs {
		fmt.Fprintf(&text, "\n## %s\n\nУзел: %s; родитель: %s\n\n%s\n", m.Role, m.ID, m.Parent, m.Text)
	}
	if err = atomicWrite(filepath.Join(s.Vault, md), []byte(text.String())); err != nil {
		return false, false, id, err
	}
	newUpdated := number(obj["update_time"])
	if !exists || newUpdated == 0 || conv.Updated == 0 || newUpdated >= conv.Updated {
		conv.ID, conv.Title, conv.SourceID = id, title, sourceID
		conv.Created, conv.Updated = number(obj["create_time"]), newUpdated
		conv.Messages, conv.Latest = len(msgs), h
	}
	conv.Revisions = append(conv.Revisions, Revision{Hash: h, JSON: filepath.ToSlash(j), Markdown: filepath.ToSlash(md), MarkdownHash: sum([]byte(text.String())), ImportedAt: now()})
	s.Cat.Conversations[id] = conv
	return true, !exists, id, nil
}
func (s *Store) AddNote(kind, text string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if kind != "memory" && kind != "instructions" && kind != "project" {
		return errors.New("неизвестный тип записи")
	}
	text = strings.TrimSpace(text)
	if text == "" || len(text) > 4<<20 {
		return errors.New("введите текст до 4 МиБ")
	}
	id := sum([]byte(kind + "\n" + text))
	for _, n := range s.Cat.Notes {
		if n.ID == id {
			return nil
		}
	}
	rel := filepath.Join("knowledge", kind+"-"+id+".md")
	if err := atomicWrite(filepath.Join(s.Vault, rel), []byte(text+"\n")); err != nil {
		return err
	}
	s.Cat.Notes = append(s.Cat.Notes, Note{ID: id, Kind: kind, Path: filepath.ToSlash(rel), Hash: sum([]byte(text + "\n")), CreatedAt: now()})
	return s.save()
}

type VerifyResult struct {
	Checked, Conversations, Notes int
	Errors                        []string
}

func (s *Store) Verify() VerifyResult {
	s.mu.RLock()
	defer s.mu.RUnlock()
	r := VerifyResult{Errors: []string{}}
	if err := s.validateFileLinks(); err != nil {
		r.Errors = append(r.Errors, err.Error())
	}
	seen := map[string]bool{}
	for _, src := range s.Cat.Sources {
		for _, e := range src.Entries {
			if seen[e.Hash] {
				continue
			}
			seen[e.Hash] = true
			h, size, err := hashFile(s.objectPath(e.Hash))
			r.Checked++
			if err != nil || h != e.Hash || size != e.Size {
				r.Errors = append(r.Errors, "отсутствует или повреждён объект "+e.Hash)
			}
		}
	}
	for _, c := range s.Cat.Conversations {
		for _, rev := range c.Revisions {
			b, err := os.ReadFile(filepath.Join(s.Vault, filepath.FromSlash(rev.JSON)))
			r.Conversations++
			if err != nil || sum(b) != rev.Hash {
				r.Errors = append(r.Errors, "повреждена версия разговора "+rev.Hash)
			}
			md, err := os.ReadFile(filepath.Join(s.Vault, filepath.FromSlash(rev.Markdown)))
			if err != nil || sum(md) != rev.MarkdownHash {
				r.Errors = append(r.Errors, "повреждён Markdown "+rev.Hash)
			}
		}
	}
	for _, n := range s.Cat.Notes {
		b, err := os.ReadFile(filepath.Join(s.Vault, filepath.FromSlash(n.Path)))
		r.Notes++
		if err != nil || sum(b) != n.Hash {
			r.Errors = append(r.Errors, "повреждена запись "+n.ID)
		}
	}
	return r
}

func validHash(h string) bool {
	if len(h) != 64 {
		return false
	}
	_, err := hex.DecodeString(h)
	return err == nil
}
func (s *Store) validate() error {
	if s.Cat.Schema != 1 || s.Cat.Sources == nil || s.Cat.Conversations == nil {
		return errors.New("неподдерживаемая схема каталога")
	}
	for key, src := range s.Cat.Sources {
		if !validHash(key) || key != src.ID {
			return errors.New("повреждён идентификатор источника")
		}
		for _, e := range src.Entries {
			if !validHash(e.Hash) || e.Size < 0 {
				return errors.New("повреждён индекс файлов")
			}
		}
	}
	for _, c := range s.Cat.Conversations {
		for _, r := range c.Revisions {
			if !validHash(r.Hash) || !validHash(r.MarkdownHash) || !safeArchivePath(r.JSON) || !safeArchivePath(r.Markdown) {
				return errors.New("повреждён индекс версий")
			}
		}
	}
	for _, n := range s.Cat.Notes {
		if !validHash(n.ID) || !validHash(n.Hash) || !safeArchivePath(n.Path) {
			return errors.New("повреждён индекс записей")
		}
	}
	return s.validateFileLinks()
}

func (s *Store) ImportFolder(folder string) (ImportResult, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	var result ImportResult
	folder, err := filepath.Abs(folder)
	if err != nil {
		return result, err
	}
	if overlap(canonicalPath(folder), canonicalPath(s.Root)) {
		return result, errors.New("выберите папку разработки отдельно от папки данных B/S Reserve")
	}
	var entries []Entry
	warnings := []string{}
	var total int64
	err = filepath.WalkDir(folder, func(p string, d os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if d.IsDir() {
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			warnings = append(warnings, "символическая ссылка пропущена")
			return nil
		}
		if len(entries) >= maxEntries {
			return errors.New("в папке более 100000 файлов")
		}
		info, e := d.Info()
		if e != nil || !info.Mode().IsRegular() {
			warnings = append(warnings, "специальный файл пропущен")
			return nil
		}
		total += info.Size()
		if total > int64(maxExpanded) {
			return errors.New("папка превышает 8 ГиБ; выберите отдельные подпапки")
		}
		f, e := os.Open(p)
		if e != nil {
			return e
		}
		item, e := s.put(f, maxSource)
		f.Close()
		if e != nil {
			return e
		}
		rel, e := filepath.Rel(folder, p)
		if e != nil {
			return e
		}
		item.Path = filepath.ToSlash(rel)
		after, e := os.Stat(p)
		if e != nil || after.Size() != info.Size() || !after.ModTime().Equal(info.ModTime()) {
			warnings = append(warnings, "файл менялся при чтении: "+safeLabel(item.Path))
		}
		entries = append(entries, item)
		return nil
	})
	if err != nil {
		return result, err
	}
	if len(entries) == 0 {
		return result, errors.New("в папке нет обычных файлов")
	}
	b, _ := json.Marshal(entries)
	id := sum(b)
	result.SourceID = id
	if _, ok := s.Cat.Sources[id]; ok {
		result.Duplicate = true
		return result, nil
	}
	manifest, err := s.put(bytes.NewReader(b), maxJSON)
	if err != nil {
		return result, err
	}
	manifest.Path = "_folder-manifest.json"
	entries = append([]Entry{manifest}, entries...)
	status := "saved"
	if len(warnings) > 0 {
		status = "partial"
	}
	s.Cat.Sources[id] = Source{ID: id, Name: filepath.Base(folder), Kind: "folder", ImportedAt: now(), Status: status, Size: total, Entries: entries, Warnings: warnings}
	result.Files = len(entries) - 1
	result.Warnings = warnings
	return result, s.save()
}

const recoveryText = "B/S Reserve 0.1.0-alpha.9 — независимое восстановление\n\n" +
	"Резервный репозиторий restic зашифрован. Рабочий каталог Vault не зашифрован.\n" +
	"Для аварийного восстановления нужны движок restic, весь репозиторий и его пароль.\n" +
	"В командной строке: restic -r \"ПУТЬ_К_РЕПОЗИТОРИЮ\" snapshots\n" +
	"Затем: restic -r \"ПУТЬ_К_РЕПОЗИТОРИЮ\" restore ID_СНИМКА --target \"НОВАЯ_ПАПКА\"\n" +
	"Windows: bin/restic.exe; Linux: bin/restic; macOS: B_S_Reserve.app/Contents/MacOS/bin/restic.\n" +
	"Используйте полный путь к комплектному движку вместо restic в примерах выше.\n" +
	"Пароль вводится по запросу restic; передавать его в аргументах не нужно.\n" +
	"Восстанавливайте в пустую новую папку. Сохраните копию пароля отдельно от ПК.\n" +
	"catalog.json описывает Sources/Entries (путь, SHA-256, размер) и версии Conversations.\nFileLinks содержит выбранные пользователем связи: ConversationID, SourceID, Index и Hash.\n" +
	"Байты файлов находятся в objects/ПЕРВЫЕ_2_СИМВОЛА_ХЕША/ПОЛНЫЙ_ХЕШ.\n" +
	"JSON и Markdown разговоров находятся в conversations/, память и инструкции — knowledge/.\n" +
	"Эти файлы читаются без ChatGPT и без B/S Reserve. Все ветви из источника сохранены в JSON.\n" +
	"Экспорт чатов не восстанавливает аккаунт OpenAI или внутреннее состояние памяти.\n"
