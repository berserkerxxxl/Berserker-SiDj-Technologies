package main

import (
	"archive/zip"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"
)

//go:embed offline.html
var offlineHTML string

func (s *Store) Migration() (any, error) {
	return s.MigrationTo("")
}

func (s *Store) MigrationTo(directory string) (any, error) {
	directory = strings.TrimSpace(directory)
	if directory == "" {
		directory = filepath.Join(s.Root, "Outbox")
	}
	if !filepath.IsAbs(directory) {
		return nil, errors.New("укажите полный путь к папке пакета переноса")
	}
	directory = filepath.Clean(directory)
	rel, err := filepath.Rel(canonicalPath(s.Vault), canonicalPath(directory))
	if err == nil && rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator)) {
		return nil, errors.New("папка пакета переноса должна находиться вне Vault")
	}
	result, err := s.migrationToDirectory(directory)
	if err != nil {
		return nil, fmt.Errorf("пакет переноса не создан в %s: %w", directory, err)
	}
	return result, nil
}

func (s *Store) migrationToDirectory(directory string) (any, error) {
	check := s.Verify()
	if len(check.Errors) > 0 {
		return nil, errors.New("сначала исправьте повреждения рабочего архива")
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	if len(s.Cat.Sources) == 0 && len(s.Cat.Notes) == 0 {
		return nil, errors.New("сначала добавьте данные")
	}
	if err := os.MkdirAll(directory, 0700); err != nil {
		return nil, err
	}
	name := "BS_Reserve_Migration_" + time.Now().UTC().Format("20060102_150405") + "_" + randomID()[:6] + ".zip"
	temp, err := os.CreateTemp(directory, ".migration-*")
	if err != nil {
		return nil, err
	}
	tmp := temp.Name()
	defer func() { _ = temp.Close(); _ = os.Remove(tmp) }()
	zw := zip.NewWriter(temp)
	addBytes := func(name string, b []byte) error {
		w, e := zw.Create(name)
		if e != nil {
			return e
		}
		_, e = w.Write(b)
		return e
	}
	addFile := func(name, p string) error {
		f, e := os.Open(p)
		if e != nil {
			return e
		}
		defer f.Close()
		w, e := zw.Create(name)
		if e != nil {
			return e
		}
		_, e = io.Copy(w, f)
		return e
	}
	err = filepath.WalkDir(s.Vault, func(p string, d os.DirEntry, e error) error {
		if e != nil {
			return e
		}
		if d.IsDir() {
			return nil
		}
		if d.Type()&os.ModeSymlink != 0 {
			return errors.New("неожиданная символическая ссылка в Vault")
		}
		rel, e := filepath.Rel(s.Vault, p)
		if e != nil {
			return e
		}
		return addFile("Vault/"+filepath.ToSlash(rel), p)
	})
	if err != nil {
		zw.Close()
		temp.Close()
		return nil, err
	}
	type archivedChat struct {
		ID, Title   string
		Messages    []Message
		Versions    int
		Attachments []Attachment
	}
	assets := s.indexAssets()
	chats := []archivedChat{}
	for _, c := range s.Cat.Conversations {
		for _, rev := range c.Revisions {
			if rev.Hash != c.Latest {
				continue
			}
			b, e := os.ReadFile(filepath.Join(s.Vault, filepath.FromSlash(rev.JSON)))
			if e != nil {
				zw.Close()
				temp.Close()
				return nil, e
			}
			var obj map[string]any
			if e = json.Unmarshal(b, &obj); e != nil {
				zw.Close()
				temp.Close()
				return nil, e
			}
			msgs, attachments := messagesWithAssets(obj, c.ID, assets)
			chats = append(chats, archivedChat{ID: c.ID, Title: c.Title, Messages: msgs, Versions: len(c.Revisions), Attachments: attachments})
		}
	}
	type archivedFile struct {
		Name, Path, Hash, SourcePath, SourceID string
		Size                                   int64
	}
	type mappingReport struct {
		SourceID string
		AssetNameReport
	}
	mappingReports := []mappingReport{}
	files := []archivedFile{}
	seen := map[string]bool{}
	for _, src := range s.Cat.Sources {
		entries, report := s.namedEntries(src)
		if report.Declared != 0 || len(report.Warnings) != 0 {
			mappingReports = append(mappingReports, mappingReport{SourceID: src.ID, AssetNameReport: report})
		}
		for _, e := range entries {
			dest := assetExportPath(e.Hash, entryName(e))
			if seen[dest] {
				continue
			}
			seen[dest] = true
			if err = addFile(dest, s.objectPath(e.Hash)); err != nil {
				zw.Close()
				temp.Close()
				return nil, err
			}
			files = append(files, archivedFile{Name: entryName(e), Path: dest, Hash: e.Hash, Size: e.Size, SourcePath: e.Path, SourceID: src.ID})
		}
	}
	manifest, _ := json.MarshalIndent(map[string]any{"Schema": 1, "Version": Version, "Build": Build, "Files": files, "AssetMappings": mappingReports, "FileLinks": s.Cat.FileLinks}, "", "  ")
	data, _ := json.Marshal(map[string]any{"Chats": chats, "Files": files, "Created": now(), "Notes": s.Cat.Notes, "AssetMappings": mappingReports})
	if err = addBytes("FILES_MANIFEST.json", manifest); err == nil {
		err = addBytes("index.html", []byte(strings.ReplaceAll(offlineHTML, "__ARCHIVE_DATA__", string(data))))
	}
	if err == nil {
		err = addBytes("favicon.ico", faviconICO)
	}
	if err == nil {
		err = addBytes("START_HERE_RU.txt", []byte("Это НЕЗАШИФРОВАННЫЙ пакет переноса B/S Reserve.\nОткройте index.html: чтение и поиск работают без сети.\nVault содержит исходные данные, все версии и записи памяти.\nfiles содержит оригиналы с восстановленными именами.\nДля нового ChatGPT выбирайте нужные файлы и инструкции; старый аккаунт не воссоздаётся.\nДля локальной LLM используйте JSON/Markdown и оригиналы документов.\n"+recoveryText))
	}
	if err == nil {
		err = zw.Close()
	} else {
		_ = zw.Close()
	}
	if err == nil {
		err = temp.Sync()
	}
	ce := temp.Close()
	if err == nil {
		err = ce
	}
	if err != nil {
		return nil, err
	}
	final := filepath.Join(directory, name)
	if err = os.Rename(tmp, final); err != nil {
		return nil, err
	}
	hash, size, err := hashFile(final)
	return map[string]any{"Name": name, "SHA256": hash, "Bytes": size, "Path": final, "Encrypted": false}, err
}
