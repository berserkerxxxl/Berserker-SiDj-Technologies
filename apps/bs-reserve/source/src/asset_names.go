package main

import (
	"encoding/json"
	"io"
	"os"
	"path"
	"sort"
	"strings"
)

type AssetNameReport struct {
	Declared, Resolved int
	Missing, Warnings  []string
}

func entryName(entry Entry) string {
	if entry.OriginalName != "" {
		return entry.OriginalName
	}
	return entry.Path
}

// Resolve aliases from the original metadata of this source only. The catalog,
// source paths, hashes and stored bytes remain unchanged, including older imports.
func (s *Store) namedEntries(src Source) ([]Entry, AssetNameReport) {
	entries := append([]Entry(nil), src.Entries...)
	report := AssetNameReport{Missing: []string{}, Warnings: []string{}}
	names := map[string]string{}
	conflicts := map[string]bool{}
	for _, entry := range src.Entries {
		if pathBase(entry.Path) != "conversation_asset_file_names.json" {
			continue
		}
		f, err := os.Open(s.objectPath(entry.Hash))
		if err != nil {
			report.Warnings = append(report.Warnings, "карта исходных имён не прочитана")
			continue
		}
		data, err := io.ReadAll(io.LimitReader(f, maxJSON+1))
		f.Close()
		var mapping map[string]string
		if err != nil || int64(len(data)) > maxJSON || json.Unmarshal(data, &mapping) != nil {
			report.Warnings = append(report.Warnings, "неподдерживаемая или слишком большая карта исходных имён")
			continue
		}
		directory := path.Dir(strings.ReplaceAll(entry.Path, "\\", "/"))
		for sourcePath, original := range mapping {
			sourcePath = strings.ReplaceAll(sourcePath, "\\", "/")
			if !safeArchivePath(sourcePath) || strings.TrimSpace(original) == "" || len(original) > 4096 || strings.ContainsRune(original, 0) {
				report.Warnings = append(report.Warnings, "пропущена некорректная запись карты исходных имён")
				continue
			}
			key := path.Clean(path.Join(directory, sourcePath))
			if old, ok := names[key]; ok && old != original {
				conflicts[key] = true
			}
			names[key] = original
		}
	}
	report.Declared = len(names)
	matched := map[string]bool{}
	for i, entry := range entries {
		key := path.Clean(strings.ReplaceAll(entry.Path, "\\", "/"))
		if original, ok := names[key]; ok && !conflicts[key] {
			entries[i].OriginalName = original
			matched[key] = true
		}
	}
	report.Resolved = len(matched)
	for key := range names {
		if !matched[key] {
			report.Missing = append(report.Missing, key)
		}
	}
	if len(conflicts) != 0 {
		report.Warnings = append(report.Warnings, "противоречивые исходные имена оставлены без изменения")
	}
	sort.Strings(report.Missing)
	return entries, report
}
