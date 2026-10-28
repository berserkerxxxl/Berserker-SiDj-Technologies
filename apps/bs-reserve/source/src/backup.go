package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"
)

var ResticHash string

type Config struct {
	Repository, LastBackup, LastCheck, LastRestore, LastSnapshot string
	AutoBackup, WatchEnabled                                     bool
}
type Engine struct {
	Binary, ExpectedHash string
	once                 sync.Once
	verifyError          error
}
type Snapshot struct {
	ID, ShortID, Time string
}

func (e *Engine) verifyBinary() error {
	e.once.Do(func() {
		h, _, err := hashFile(e.Binary)
		if err != nil {
			e.verifyError = fmt.Errorf("движок restic не найден рядом с программой: %w", err)
			return
		}
		if e.ExpectedHash == "" || !strings.EqualFold(h, e.ExpectedHash) {
			e.verifyError = errors.New("не совпадает SHA-256 restic; восстановите исходный комплект")
		}
	})
	return e.verifyError
}

type tailBuffer struct{ b []byte }

func (w *tailBuffer) Write(p []byte) (int, error) {
	n := len(p)
	w.b = append(w.b, p...)
	if len(w.b) > 2<<20 {
		w.b = w.b[len(w.b)-(2<<20):]
	}
	return n, nil
}
func (e *Engine) run(dir, repo, password string, args ...string) ([]byte, error) {
	if err := e.verifyBinary(); err != nil {
		return nil, err
	}
	if password == "" {
		return nil, errors.New("введите пароль репозитория")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Hour)
	defer cancel()
	base := []string{"--no-cache", "-r", repo, "--json"}
	cmd := exec.CommandContext(ctx, e.Binary, append(base, args...)...)
	cmd.Dir = dir
	for _, v := range os.Environ() {
		if !strings.HasPrefix(v, "RESTIC_") {
			cmd.Env = append(cmd.Env, v)
		}
	}
	cmd.Env = append(cmd.Env, "RESTIC_PASSWORD="+password)
	hideCommand(cmd)
	out := &tailBuffer{}
	cmd.Stdout, cmd.Stderr = out, out
	err := cmd.Run()
	if err != nil {
		// Restic exit 3 means an incomplete backup and is deliberately an error.
		message := strings.ReplaceAll(string(out.b), password, "[скрыто]")
		if len(message) > 1200 {
			message = message[len(message)-1200:]
		}
		return out.b, fmt.Errorf("restic завершился с ошибкой (%v): %s", err, message)
	}
	return out.b, nil
}
func overlap(a, b string) bool {
	r, err := filepath.Rel(a, b)
	if err == nil && r != ".." && !strings.HasPrefix(r, ".."+string(filepath.Separator)) {
		return true
	}
	r, err = filepath.Rel(b, a)
	return err == nil && r != ".." && !strings.HasPrefix(r, ".."+string(filepath.Separator))
}
func canonicalPath(p string) string {
	if r, err := filepath.EvalSymlinks(p); err == nil {
		return r
	}
	parent := filepath.Dir(p)
	if parent == p {
		return p
	}
	return filepath.Join(canonicalPath(parent), filepath.Base(p))
}
func repositoryPath(p, vault string) (string, error) {
	if strings.TrimSpace(p) == "" || strings.Contains(p, "://") {
		return "", errors.New("укажите локальную папку резервного репозитория")
	}
	p, err := filepath.Abs(p)
	if err != nil {
		return "", err
	}
	if overlap(canonicalPath(p), canonicalPath(vault)) {
		return "", errors.New("репозиторий и рабочая папка Vault должны находиться отдельно")
	}
	return p, nil
}
func loadConfig(root string) Config {
	c := Config{WatchEnabled: true}
	if b, err := os.ReadFile(filepath.Join(root, "config", "settings.json")); err == nil {
		_ = json.Unmarshal(b, &c)
	}
	return c
}
func keyPath(root, repo string) string {
	return filepath.Join(root, "config", "keys", sum([]byte(repo))+".dat")
}
func savePassword(root, repo, password string) error {
	b, err := protectSecret([]byte(password))
	if err != nil {
		return err
	}
	return atomicWrite(keyPath(root, repo), b)
}
func rememberedPassword(root, repo string) (string, error) {
	b, err := os.ReadFile(keyPath(root, repo))
	if err != nil {
		return "", errors.New("нет сохранённого ключа; введите пароль репозитория")
	}
	p, err := unprotectSecret(b)
	if err != nil {
		return "", errors.New("ключ Windows не разблокирован; используйте аварийный пароль")
	}
	return string(p), nil
}
func (e *Engine) snapshots(dir, repo, password string) ([]Snapshot, error) {
	b, err := e.run(dir, repo, password, "snapshots", "--tag", "BS-Reserve")
	if err != nil {
		return nil, err
	}
	var raw []struct {
		ID       string
		Short_ID string
		Time     string
	}
	// JSON field short_id does not map to Short_ID consistently through aliases.
	var data []map[string]any
	if err = json.Unmarshal(b, &data); err != nil {
		return nil, err
	}
	_ = raw
	out := []Snapshot{}
	for _, v := range data {
		out = append(out, Snapshot{ID: str(v["id"]), ShortID: str(v["short_id"]), Time: str(v["time"])})
	}
	return out, nil
}
func (e *Engine) backup(s *Store, repo, password string) (string, error) {
	check := s.Verify()
	if len(check.Errors) > 0 {
		return "", errors.New("рабочий архив повреждён; сначала восстановите файлы из проверенной копии")
	}
	s.mu.RLock()
	defer s.mu.RUnlock()
	if len(s.Cat.Sources) == 0 && len(s.Cat.Notes) == 0 {
		return "", errors.New("сначала добавьте выгрузку, файлы или запись памяти")
	}
	b, err := e.run(s.Root, repo, password, "backup", "--tag", "BS-Reserve", "--host", "BS-Reserve", "Vault")
	if err != nil {
		return "", err
	}
	var id string
	for _, line := range bytes.Split(b, []byte{'\n'}) {
		var v map[string]any
		if json.Unmarshal(line, &v) == nil && str(v["snapshot_id"]) != "" {
			id = str(v["snapshot_id"])
		}
	}
	if id == "" {
		return "", errors.New("restic не вернул идентификатор снимка")
	}
	return id, nil
}

var snapshotPattern = regexp.MustCompile("^[a-fA-F0-9]{8,64}$")

func (e *Engine) restore(s *Store, repo, password, id, target string) (VerifyResult, error) {
	var result VerifyResult
	if !snapshotPattern.MatchString(id) {
		return result, errors.New("выберите идентификатор снимка")
	}
	if strings.TrimSpace(target) == "" {
		return result, errors.New("укажите новую пустую папку восстановления")
	}
	target, err := filepath.Abs(target)
	if err != nil {
		return result, err
	}
	if overlap(canonicalPath(target), canonicalPath(s.Root)) || overlap(canonicalPath(target), canonicalPath(repo)) {
		return result, errors.New("папка восстановления должна быть отдельно от данных и репозитория")
	}
	if entries, err := os.ReadDir(target); err == nil && len(entries) > 0 {
		return result, errors.New("папка восстановления должна быть пустой")
	} else if err != nil && !os.IsNotExist(err) {
		return result, err
	}
	if err = os.MkdirAll(target, 0700); err != nil {
		return result, err
	}
	if _, err = e.run(s.Root, repo, password, "restore", id, "--target", target); err != nil {
		return result, err
	}
	restored := &Store{Root: target, Vault: filepath.Join(target, "Vault")}
	b, err := os.ReadFile(filepath.Join(restored.Vault, "catalog.json"))
	if err != nil {
		return result, errors.New("в восстановлении не найден каталог Vault/catalog.json")
	}
	if err = json.Unmarshal(b, &restored.Cat); err != nil {
		return result, err
	}
	if err = restored.validate(); err != nil {
		return result, err
	}
	result = restored.Verify()
	if len(result.Errors) > 0 {
		return result, errors.New("восстановление не прошло сверку файлов и версий")
	}
	return result, nil
}
