package main

import (
	"encoding/json"
	"fmt"
	"path"
	"regexp"
	"sort"
	"strings"
)

type Attachment struct {
	Name, Path, Hash, SourcePath, SourceID string
	Size                                   int64
	Index                                  int
}

type assetIndex struct {
	byToken        map[string][]Attachment
	byConversation map[string][]Attachment
}

var assetToken = regexp.MustCompile(`(?:^|[^A-Za-z0-9_-])(file[_-][A-Za-z0-9_-]+)`)

func assetExportPath(hash, name string) string {
	return "files/" + hash + "/" + portableName(pathBase(name))
}

func appendAsset(list []Attachment, item Attachment) []Attachment {
	for _, old := range list {
		if old.Path == item.Path {
			return list
		}
	}
	return append(list, item)
}

// Imported identifiers and explicit user selections establish relationships.
// Display names alone never create a relationship.
func (s *Store) indexAssets() *assetIndex {
	index := &assetIndex{byToken: map[string][]Attachment{}, byConversation: map[string][]Attachment{}}
	manual := map[string]map[int][]string{}
	for _, link := range s.Cat.FileLinks {
		if manual[link.SourceID] == nil {
			manual[link.SourceID] = map[int][]string{}
		}
		manual[link.SourceID][link.Index] = append(manual[link.SourceID][link.Index], link.ConversationID)
	}
	for _, src := range s.Cat.Sources {
		entries, _ := s.namedEntries(src)
		for i, entry := range entries {
			name := entryName(entry)
			item := Attachment{Name: name, Path: assetExportPath(entry.Hash, name), Hash: entry.Hash, Size: entry.Size, SourcePath: entry.Path, SourceID: src.ID, Index: i}
			for _, conversationID := range manual[src.ID][i] {
				index.byConversation[conversationID] = appendAsset(index.byConversation[conversationID], item)
			}
			base := pathBase(entry.Path)
			stem := strings.TrimSuffix(base, path.Ext(base))
			if strings.HasPrefix(stem, "file_") || strings.HasPrefix(stem, "file-") {
				index.byToken[stem] = appendAsset(index.byToken[stem], item)
			}
			parts := strings.SplitN(strings.ReplaceAll(name, "\\", "/"), "/", 2)
			if len(parts) == 2 {
				if _, exists := s.Cat.Conversations[parts[0]]; exists {
					index.byConversation[parts[0]] = appendAsset(index.byConversation[parts[0]], item)
				}
			}
		}
	}
	for _, group := range []map[string][]Attachment{index.byToken, index.byConversation} {
		for key := range group {
			sort.Slice(group[key], func(i, j int) bool { return group[key][i].Path < group[key][j].Path })
		}
	}
	return index
}

func messagesWithAssets(obj map[string]any, conversationID string, index *assetIndex) ([]Message, []Attachment) {
	result := messages(obj)
	rawMessages := map[string]any{}
	if mapping, ok := obj["mapping"].(map[string]any); ok {
		for id, value := range mapping {
			if node, ok := value.(map[string]any); ok {
				rawMessages[id] = node["message"]
			}
		}
	} else if list, ok := obj["messages"].([]any); ok {
		for i, value := range list {
			rawMessages[fmt.Sprint(i)] = value
		}
	}
	all := append([]Attachment(nil), index.byConversation[conversationID]...)
	for i, message := range result {
		data, _ := json.Marshal(rawMessages[message.ID])
		for _, match := range assetToken.FindAllSubmatch(data, -1) {
			for _, item := range index.byToken[string(match[1])] {
				result[i].Attachments = appendAsset(result[i].Attachments, item)
				all = appendAsset(all, item)
			}
		}
	}
	return result, all
}
