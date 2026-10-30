package main

import (
	"encoding/json"
	"errors"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// FileLink records an explicit user choice without changing exported messages.
// The hash guards the stable source-entry reference against catalog corruption.
type FileLink struct {
	ConversationID, SourceID, Hash, AddedAt string
	Index                                   int
}

type FileChoice struct {
	Attachment
	SourceName     string
	Linked, Manual bool
}

func (s *Store) validateFileLinks() error {
	seen := map[string]map[string]map[int]bool{}
	for _, link := range s.Cat.FileLinks {
		src, exists := s.Cat.Sources[link.SourceID]
		_, conversationExists := s.Cat.Conversations[link.ConversationID]
		if !exists || !conversationExists || link.Index < 0 || link.Index >= len(src.Entries) || src.Entries[link.Index].Hash != link.Hash {
			return errors.New("повреждена привязка файла к чату")
		}
		if seen[link.ConversationID] == nil {
			seen[link.ConversationID] = map[string]map[int]bool{}
		}
		if seen[link.ConversationID][link.SourceID] == nil {
			seen[link.ConversationID][link.SourceID] = map[int]bool{}
		}
		if seen[link.ConversationID][link.SourceID][link.Index] {
			return errors.New("повторяется привязка файла к чату")
		}
		seen[link.ConversationID][link.SourceID][link.Index] = true
	}
	return nil
}

func (s *Store) SetFileLink(conversationID, sourceID string, index int, remove bool) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, exists := s.Cat.Conversations[conversationID]; !exists {
		return false, errors.New("чат для привязки не найден")
	}
	src, exists := s.Cat.Sources[sourceID]
	if !exists || index < 0 || index >= len(src.Entries) {
		return false, errors.New("сохранённый файл не найден")
	}
	previous := s.Cat.FileLinks
	links := make([]FileLink, 0, len(previous)+1)
	found := false
	for _, link := range previous {
		if link.ConversationID == conversationID && link.SourceID == sourceID && link.Index == index {
			found = true
			if remove {
				continue
			}
		}
		links = append(links, link)
	}
	if (!remove && found) || (remove && !found) {
		return false, nil
	}
	if !remove {
		links = append(links, FileLink{ConversationID: conversationID, SourceID: sourceID, Index: index, Hash: src.Entries[index].Hash, AddedAt: now()})
	}
	s.Cat.FileLinks = links
	if err := s.save(); err != nil {
		s.Cat.FileLinks = previous
		return false, err
	}
	return true, nil
}

func (s *Store) FileChoices(conversationID, query string) ([]FileChoice, int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	c, exists := s.Cat.Conversations[conversationID]
	if !exists {
		return nil, 0, errors.New("чат для привязки не найден")
	}
	query = strings.ToLower(strings.TrimSpace(query))
	if len(query) > 1024 {
		return nil, 0, errors.New("сократите строку поиска файла")
	}
	var obj map[string]any
	for _, rev := range c.Revisions {
		if rev.Hash == c.Latest {
			b, err := os.ReadFile(filepath.Join(s.Vault, filepath.FromSlash(rev.JSON)))
			if err != nil {
				return nil, 0, err
			}
			if err := json.Unmarshal(b, &obj); err != nil {
				return nil, 0, err
			}
			break
		}
	}
	_, attached := messagesWithAssets(obj, conversationID, s.indexAssets())
	linked := map[string]bool{}
	for _, item := range attached {
		linked[item.Path] = true
	}
	manual := map[string]map[int]bool{}
	for _, link := range s.Cat.FileLinks {
		if link.ConversationID == conversationID {
			if manual[link.SourceID] == nil {
				manual[link.SourceID] = map[int]bool{}
			}
			manual[link.SourceID][link.Index] = true
		}
	}
	choices := []FileChoice{}
	for _, src := range s.Cat.Sources {
		entries, _ := s.namedEntries(src)
		for i, entry := range entries {
			name := entryName(entry)
			if query != "" && !strings.Contains(strings.ToLower(name+"\n"+entry.Path+"\n"+src.Name), query) {
				continue
			}
			item := Attachment{Name: name, Path: assetExportPath(entry.Hash, name), Hash: entry.Hash, Size: entry.Size, SourcePath: entry.Path, SourceID: src.ID, Index: i}
			choices = append(choices, FileChoice{Attachment: item, SourceName: src.Name, Linked: linked[item.Path], Manual: manual[src.ID][i]})
		}
	}
	sort.Slice(choices, func(i, j int) bool {
		a, b := choices[i], choices[j]
		if a.Name != b.Name {
			return a.Name < b.Name
		}
		if a.SourceID != b.SourceID {
			return a.SourceID < b.SourceID
		}
		return a.Index < b.Index
	})
	total := len(choices)
	if len(choices) > 100 {
		choices = choices[:100]
	}
	return choices, total, nil
}

func (a *App) files(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		a.fail(w, http.StatusMethodNotAllowed, errors.New("нужен GET"))
		return
	}
	choices, total, err := a.store.FileChoices(r.URL.Query().Get("conversation"), r.URL.Query().Get("q"))
	if err != nil {
		a.fail(w, http.StatusBadRequest, err)
		return
	}
	respond(w, map[string]any{"Files": choices, "Total": total})
}
