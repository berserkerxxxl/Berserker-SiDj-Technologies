package main

import (
	"bytes"
	"context"
	"crypto/rand"
	_ "embed"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"mime"
	"net"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"
)

//go:embed ui.html
var uiHTML string

type Job struct {
	ID, Action, Started, Finished, Error string
	Running                              bool
	Result                               any
}
type App struct {
	store               *Store
	engine              *Engine
	exe, token, baseURL string
	mu                  sync.Mutex
	logMu               sync.Mutex
	cfg                 Config
	job                 Job
	seen                map[string]string
	migrationPaths      map[string]string
	pickerMu            sync.Mutex
	picker              func(context.Context, string) (string, error)
	shutdown            func()
}

func randomID() string {
	b := make([]byte, 24)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}
func (a *App) log(action, status string, result any) {
	if a.store == nil {
		return
	}
	a.logMu.Lock()
	defer a.logMu.Unlock()
	f, err := os.OpenFile(filepath.Join(a.store.Root, "logs", "operations.jsonl"), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return
	}
	defer f.Close()
	_ = json.NewEncoder(f).Encode(map[string]any{"Time": now(), "Action": action, "Status": status, "Result": result})
}
func (a *App) updateConfig(change func(*Config)) error {
	a.mu.Lock()
	defer a.mu.Unlock()
	cfg := a.cfg
	change(&cfg)
	if err := writeJSON(filepath.Join(a.store.Root, "config", "settings.json"), cfg); err != nil {
		return err
	}
	a.cfg = cfg
	return nil
}
func (a *App) startJob(action string, work func() (any, error)) error {
	a.mu.Lock()
	if a.job.Running {
		a.mu.Unlock()
		return errors.New("другая операция уже выполняется")
	}
	a.job = Job{ID: randomID(), Action: action, Started: now(), Running: true}
	a.mu.Unlock()
	a.log(action, "started", nil)
	go func() {
		result, err := work()
		status := "completed"
		message := ""
		if err != nil {
			status = "error"
			message = userError(err)
		}
		a.mu.Lock()
		a.job.Running = false
		a.job.Finished = now()
		a.job.Result = result
		a.job.Error = message
		a.mu.Unlock()
		if err != nil {
			a.log(action, status, recordError(err))
		} else {
			a.log(action, status, result)
		}
	}()
	return nil
}
func respond(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	_ = json.NewEncoder(w).Encode(v)
}
func (a *App) fail(w http.ResponseWriter, status int, err error) {
	if status != http.StatusForbidden {
		a.log("request", "error", recordError(err))
	}
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	respond(w, map[string]any{"Error": userError(err)})
}
func (a *App) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/" {
			http.NotFound(w, r)
			return
		}
		w.Header().Set("Content-Type", "text/html; charset=utf-8")
		_, _ = io.WriteString(w, strings.ReplaceAll(uiHTML, "__BS_TOKEN__", a.token))
	})
	mux.HandleFunc("/api/state", a.state)
	mux.HandleFunc("/api/job", func(w http.ResponseWriter, r *http.Request) { a.mu.Lock(); j := a.job; a.mu.Unlock(); respond(w, j) })
	mux.HandleFunc("/api/upload", a.upload)
	mux.HandleFunc("/api/action", a.action)
	mux.HandleFunc("/api/conversation", a.conversation)
	mux.HandleFunc("/api/search", a.search)
	mux.HandleFunc("/api/source", a.source)
	mux.HandleFunc("/api/file", a.file)
	mux.HandleFunc("/api/download", a.download)
	mux.HandleFunc("/api/pick-folder", a.chooseFolder)
	mux.HandleFunc("/api/log", func(w http.ResponseWriter, r *http.Request) {
		a.logMu.Lock()
		b, _ := os.ReadFile(filepath.Join(a.store.Root, "logs", "operations.jsonl"))
		a.logMu.Unlock()
		lines := strings.Split(strings.TrimSpace(string(b)), "\n")
		if len(lines) > 150 {
			lines = lines[len(lines)-150:]
		}
		respond(w, map[string]any{"Lines": logLinesForUI(lines)})
	})
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Cache-Control", "no-store")
		w.Header().Set("X-Content-Type-Options", "nosniff")
		w.Header().Set("Referrer-Policy", "no-referrer")
		w.Header().Set("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
		if r.Host != "" {
			host, _, err := net.SplitHostPort(r.Host)
			if err != nil || host != "127.0.0.1" {
				a.fail(w, 403, errors.New("неразрешённый адрес сервера"))
				return
			}
		}
		if strings.HasPrefix(r.URL.Path, "/api/") {
			if r.Header.Get("X-BS-Token") != a.token {
				a.fail(w, 403, errors.New("нет доступа к локальному сеансу"))
				return
			}
			if origin := r.Header.Get("Origin"); origin != "" {
				u, err := url.Parse(origin)
				if err != nil || u.Scheme != "http" || u.Host != r.Host {
					a.fail(w, 403, errors.New("запрос с другого сайта отклонён"))
					return
				}
			}
			if site := r.Header.Get("Sec-Fetch-Site"); site == "cross-site" {
				a.fail(w, 403, errors.New("межсайтовый запрос отклонён"))
				return
			}
		}
		mux.ServeHTTP(w, r)
	})
}
func (a *App) state(w http.ResponseWriter, r *http.Request) {
	a.mu.Lock()
	cfg := a.cfg
	a.mu.Unlock()
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	sources := []map[string]any{}
	convos := []Conversation{}
	var bytes int64
	for _, s := range a.store.Cat.Sources {
		sources = append(sources, map[string]any{"ID": s.ID, "Name": s.Name, "Kind": s.Kind, "Status": s.Status, "ImportedAt": s.ImportedAt, "Files": len(s.Entries), "Warnings": s.Warnings, "Size": s.Size})
		bytes += s.Size
	}
	for _, c := range a.store.Cat.Conversations {
		convos = append(convos, c)
	}
	sort.Slice(sources, func(i, j int) bool { return str(sources[i]["ImportedAt"]) > str(sources[j]["ImportedAt"]) })
	sort.Slice(convos, func(i, j int) bool { return convos[i].Updated > convos[j].Updated })
	_, keyErr := os.Stat(keyPath(a.store.Root, cfg.Repository))
	respond(w, map[string]any{"Version": Version, "Build": Build, "Root": a.store.Root, "Inbox": filepath.Join(a.store.Root, "Inbox"), "Config": cfg, "Sources": sources, "Conversations": convos, "Notes": a.store.Cat.Notes, "Bytes": bytes, "Remembered": keyErr == nil, "Windows": runtime.GOOS == "windows", "OS": runtime.GOOS, "Arch": runtime.GOARCH, "FolderPicker": folderPickerAvailable()})
}
func (a *App) upload(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		a.fail(w, 405, errors.New("нужен POST"))
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, maxSource+(2<<20))
	reader, err := r.MultipartReader()
	if err != nil {
		a.fail(w, 400, err)
		return
	}
	part, err := reader.NextPart()
	if err != nil || part.FileName() == "" {
		a.fail(w, 400, errors.New("не выбран файл"))
		return
	}
	name := portableName(part.FileName())
	temp, err := os.CreateTemp(filepath.Join(a.store.Root, "Inbox"), ".upload-*")
	if err != nil {
		a.fail(w, 500, err)
		return
	}
	tmp := temp.Name()
	defer os.Remove(tmp)
	n, err := io.Copy(temp, io.LimitReader(part, maxSource+1))
	if err == nil && n > maxSource {
		err = errors.New("файл превышает 2 ГиБ")
	}
	if err == nil {
		err = temp.Sync()
	}
	ce := temp.Close()
	if err == nil {
		err = ce
	}
	if err != nil {
		a.fail(w, 400, err)
		return
	}
	dest := filepath.Join(a.store.Root, "Inbox", randomID()[:10]+"_"+name)
	if err = os.Rename(tmp, dest); err != nil {
		a.fail(w, 500, err)
		return
	}
	err = a.startJob("import", func() (any, error) {
		result, err := a.store.ImportFile(dest)
		if err == nil && !result.Duplicate {
			err = a.backupIfEnabled()
		}
		return result, err
	})
	if err != nil {
		respond(w, map[string]any{"Queued": true, "Message": "Файл принят в Inbox; его подберёт следующий запуск или кнопка «Обработать Inbox»"})
		return
	}
	respond(w, map[string]any{"Started": true})
}

type ActionRequest struct {
	Action, Repository, Password, Confirm, Snapshot, Target, Folder, Kind, Text string
	ScheduleTime                                                                string
	ScheduleAtLogon                                                             bool
	Remember, AutoBackup, WatchEnabled                                          bool
}

func (a *App) action(w http.ResponseWriter, r *http.Request) {
	if r.Method != "POST" {
		a.fail(w, 405, errors.New("нужен POST"))
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 5<<20)
	var req ActionRequest
	dec := json.NewDecoder(r.Body)
	dec.DisallowUnknownFields()
	if err := dec.Decode(&req); err != nil {
		a.fail(w, 400, err)
		return
	}
	work := func() (any, error) {
		switch req.Action {
		case "scan":
			return a.scan()
		case "run-once":
			return nil, a.runOnce()
		case "verify":
			result := a.store.Verify()
			if len(result.Errors) > 0 {
				return result, errors.New("проверка нашла повреждённые или отсутствующие файлы")
			}
			return result, nil
		case "note":
			return nil, a.store.AddNote(req.Kind, req.Text)
		case "folder":
			result, err := a.store.ImportFolder(req.Folder)
			if err == nil && !result.Duplicate {
				err = a.backupIfEnabled()
			}
			return result, err
		case "migration":
			result, err := a.store.MigrationTo(req.Target)
			if err != nil {
				return nil, err
			}
			item := result.(map[string]any)
			a.mu.Lock()
			if a.migrationPaths == nil {
				a.migrationPaths = map[string]string{}
			}
			a.migrationPaths[item["Name"].(string)] = item["Path"].(string)
			a.mu.Unlock()
			if err = a.updateConfig(func(c *Config) { c.MigrationDirectory = strings.TrimSpace(req.Target) }); err != nil {
				item["Warning"] = "Пакет создан, но папку вывода не удалось запомнить. " + userError(err)
				a.log("migration", "warning", recordError(err))
			}
			return item, nil
		case "demo":
			list, err := os.ReadDir(filepath.Join(filepath.Dir(a.exe), "examples"))
			if err != nil {
				return nil, err
			}
			results := []ImportResult{}
			for _, f := range list {
				if strings.HasSuffix(f.Name(), ".zip") || strings.HasSuffix(f.Name(), ".json") {
					result, e := a.store.ImportFile(filepath.Join(filepath.Dir(a.exe), "examples", f.Name()))
					if e != nil {
						return results, e
					}
					results = append(results, result)
				}
			}
			return results, nil
		case "schedule":
			at := req.ScheduleTime
			if at == "" {
				at = "19:00"
			}
			if err := validateScheduleTime(at); err != nil {
				return nil, err
			}
			if err := installSchedule(a.exe, a.store.Root, at, req.ScheduleAtLogon); err != nil {
				return nil, err
			}
			if err := a.updateConfig(func(c *Config) { c.ScheduleTime = at; c.ScheduleAtLogon = req.ScheduleAtLogon }); err != nil {
				return nil, fmt.Errorf("задача Windows обновлена, но настройки интерфейса не сохранены: %w", err)
			}
			message := "Расписание Windows: ежедневно в " + at + " по времени этого ПК"
			if req.ScheduleAtLogon {
				message += " и при входе пользователя"
			}
			return message, nil
		case "settings":
			if req.AutoBackup {
				if runtime.GOOS != "windows" {
					return nil, errors.New("в этой альфе macOS и Linux шифрованные копии запускаются вручную с вводом пароля; автоматический приём Inbox доступен")
				}
				a.mu.Lock()
				repo := a.cfg.Repository
				a.mu.Unlock()
				if _, err := rememberedPassword(a.store.Root, repo); err != nil {
					return nil, errors.New("для автоматической зашифрованной копии сначала сохраните ключ на этом ПК")
				}
			}
			err := a.updateConfig(func(c *Config) { c.AutoBackup = req.AutoBackup; c.WatchEnabled = req.WatchEnabled })
			return nil, err
		case "shutdown":
			go func() { time.Sleep(400 * time.Millisecond); a.shutdown() }()
			return "Программа остановлена; вкладку можно закрыть", nil
		}
		if req.Action != "init" && req.Action != "backup" && req.Action != "check" && req.Action != "check-full" && req.Action != "snapshots" && req.Action != "restore" {
			return nil, errors.New("неизвестная операция")
		}
		a.mu.Lock()
		cfg := a.cfg
		a.mu.Unlock()
		repo := req.Repository
		if repo == "" {
			repo = cfg.Repository
		}
		repo, err := repositoryPath(repo, a.store.Vault)
		if err != nil {
			return nil, err
		}
		password := req.Password
		if password == "" {
			if runtime.GOOS != "windows" {
				return nil, errors.New("введите пароль репозитория; macOS и Linux в этой альфе не сохраняют ключ")
			}
			password, err = rememberedPassword(a.store.Root, repo)
			if err != nil {
				return nil, err
			}
		}
		if req.Action == "init" {
			if len([]rune(password)) < 12 {
				return nil, errors.New("для нового репозитория нужен пароль не короче 12 символов")
			}
			if password != req.Confirm {
				return nil, errors.New("пароли не совпали")
			}
			if _, err = a.engine.run(a.store.Root, repo, password, "init"); err != nil {
				return nil, err
			}
		} else {
			if _, err = a.engine.run(a.store.Root, repo, password, "cat", "config"); err != nil {
				return nil, err
			}
		}
		if req.Remember {
			if err = savePassword(a.store.Root, repo, password); err != nil {
				return nil, err
			}
		}
		if err = a.updateConfig(func(c *Config) { c.Repository = repo }); err != nil {
			return nil, err
		}
		switch req.Action {
		case "init":
			return map[string]any{"Repository": repo, "Message": "Репозиторий создан. Сохраните аварийный пароль отдельно."}, nil
		case "snapshots":
			return a.engine.snapshots(a.store.Root, repo, password)
		case "backup":
			id, err := a.engine.backup(a.store, repo, password)
			if err != nil {
				return nil, err
			}
			if err = a.updateConfig(func(c *Config) { c.LastBackup = now(); c.LastSnapshot = id }); err != nil {
				return nil, err
			}
			if _, err = a.engine.run(a.store.Root, repo, password, "check"); err != nil {
				return map[string]any{"Snapshot": id}, err
			}
			if err = a.updateConfig(func(c *Config) { c.LastCheck = now() }); err != nil {
				return nil, err
			}
			return map[string]any{"Snapshot": id, "Check": "Структура репозитория проверена; полное чтение — отдельная операция"}, nil
		case "check", "check-full":
			args := []string{"check"}
			if req.Action == "check-full" {
				args = append(args, "--read-data")
			}
			if _, err = a.engine.run(a.store.Root, repo, password, args...); err != nil {
				return nil, err
			}
			err = a.updateConfig(func(c *Config) { c.LastCheck = now() })
			return map[string]any{"Full": req.Action == "check-full"}, err
		case "restore":
			result, err := a.engine.restore(a.store, repo, password, req.Snapshot, req.Target)
			if err != nil {
				return result, err
			}
			err = a.updateConfig(func(c *Config) { c.LastRestore = now() })
			return result, err
		}
		return nil, nil
	}
	if err := a.startJob(req.Action, work); err != nil {
		a.fail(w, 409, err)
		return
	}
	respond(w, map[string]any{"Started": true})
}
func (a *App) conversation(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	c, ok := a.store.Cat.Conversations[id]
	if !ok {
		a.fail(w, 404, errors.New("разговор не найден"))
		return
	}
	h := r.URL.Query().Get("revision")
	if h == "" {
		h = c.Latest
	}
	for _, rev := range c.Revisions {
		if rev.Hash == h {
			b, err := os.ReadFile(filepath.Join(a.store.Vault, filepath.FromSlash(rev.JSON)))
			if err != nil {
				a.fail(w, 500, err)
				return
			}
			var obj map[string]any
			if json.Unmarshal(b, &obj) != nil {
				a.fail(w, 500, errors.New("JSON не прочитан"))
				return
			}
			msgs, attachments := messagesWithAssets(obj, c.ID, a.store.indexAssets())
			respond(w, map[string]any{"Conversation": c, "Revision": h, "Messages": msgs, "Attachments": attachments})
			return
		}
	}
	a.fail(w, 404, errors.New("версия не найдена"))
}

func (a *App) search(w http.ResponseWriter, r *http.Request) {
	q := strings.ToLower(strings.TrimSpace(r.URL.Query().Get("q")))
	if len(q) < 2 || len(q) > 1000 {
		a.fail(w, 400, errors.New("запрос должен содержать от 2 до 1000 байт"))
		return
	}
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	results := []Conversation{}
	for _, c := range a.store.Cat.Conversations {
		found := strings.Contains(strings.ToLower(c.Title), q)
		if !found {
			for _, rev := range c.Revisions {
				if rev.Hash != c.Latest {
					continue
				}
				b, err := os.ReadFile(filepath.Join(a.store.Vault, filepath.FromSlash(rev.JSON)))
				if err != nil {
					continue
				}
				var obj map[string]any
				if json.Unmarshal(b, &obj) != nil {
					continue
				}
				for _, m := range messages(obj) {
					if strings.Contains(strings.ToLower(m.Text), q) {
						found = true
						break
					}
				}
			}
		}
		if found {
			results = append(results, c)
		}
		if len(results) >= 500 {
			break
		}
	}
	sort.Slice(results, func(i, j int) bool { return results[i].Updated > results[j].Updated })
	respond(w, map[string]any{"Conversations": results, "Limit": 500})
}
func (a *App) source(w http.ResponseWriter, r *http.Request) {
	a.store.mu.RLock()
	defer a.store.mu.RUnlock()
	s, ok := a.store.Cat.Sources[r.URL.Query().Get("id")]
	if !ok {
		a.fail(w, 404, errors.New("источник не найден"))
		return
	}
	entries, report := a.store.namedEntries(s)
	s.Entries = entries
	s.Warnings = append([]string(nil), s.Warnings...)
	for i, warning := range s.Warnings {
		s.Warnings[i] = userError(errors.New(warning))
	}
	respond(w, struct {
		Source
		AssetNames AssetNameReport
	}{s, report})
}
func (a *App) file(w http.ResponseWriter, r *http.Request) {
	index, err := strconv.Atoi(r.URL.Query().Get("index"))
	if err != nil {
		a.fail(w, 400, err)
		return
	}
	a.store.mu.RLock()
	s, ok := a.store.Cat.Sources[r.URL.Query().Get("source")]
	a.store.mu.RUnlock()
	if !ok || index < 0 || index >= len(s.Entries) {
		a.fail(w, 404, errors.New("файл не найден"))
		return
	}
	entries, _ := a.store.namedEntries(s)
	entry := entries[index]
	w.Header().Set("Content-Type", "application/octet-stream")
	w.Header().Set("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": portableName(pathBase(entryName(entry)))}))
	http.ServeFile(w, r, a.store.objectPath(entry.Hash))
}
func pathBase(p string) string { return filepath.Base(strings.ReplaceAll(p, "\\", "/")) }
func (a *App) download(w http.ResponseWriter, r *http.Request) {
	name := r.URL.Query().Get("name")
	if name != filepath.Base(name) || !strings.HasPrefix(name, "BS_Reserve_Migration_") || !strings.HasSuffix(name, ".zip") {
		a.fail(w, 400, errors.New("неверное имя пакета"))
		return
	}
	a.mu.Lock()
	p := a.migrationPaths[name]
	a.mu.Unlock()
	if p == "" {
		p = filepath.Join(a.store.Root, "Outbox", name)
	}
	w.Header().Set("Content-Type", "application/zip")
	w.Header().Set("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": name}))
	http.ServeFile(w, r, p)
}
func portableName(name string) string {
	name = pathBase(name)
	var b strings.Builder
	for _, r := range name {
		if r < 32 || strings.ContainsRune("<>:\"/\\|?*", r) {
			b.WriteRune('_')
		} else {
			b.WriteRune(r)
		}
	}
	n := strings.Trim(b.String(), " .")
	if len([]rune(n)) > 150 {
		ext := filepath.Ext(n)
		if len([]rune(ext)) > 20 {
			ext = ""
		}
		stem := strings.TrimSuffix(n, ext)
		n = string([]rune(stem)[:150-len([]rune(ext))]) + ext
	}
	// Also fit UTF-8 filesystems, whose component limit is counted in bytes.
	if len(n) > 200 {
		ext := filepath.Ext(n)
		if len(ext) > 60 {
			ext = ""
		}
		stem := []rune(strings.TrimSuffix(n, ext))
		for len(string(stem))+len(ext) > 200 {
			stem = stem[:len(stem)-1]
		}
		n = string(stem) + ext
	}
	if n == "" {
		n = "file.bin"
	}
	switch strings.ToUpper(strings.Split(n, ".")[0]) {
	case "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9":
		n = "_" + n
	}
	return n
}
func (a *App) scan() (any, error) {
	list, err := os.ReadDir(filepath.Join(a.store.Root, "Inbox"))
	if err != nil {
		return nil, err
	}
	results := []ImportResult{}
	for _, e := range list {
		if e.IsDir() || strings.HasPrefix(e.Name(), ".") {
			continue
		}
		ext := strings.ToLower(filepath.Ext(e.Name()))
		if ext == ".part" || ext == ".tmp" || ext == ".crdownload" {
			continue
		}
		info, err := e.Info()
		if err != nil || !info.Mode().IsRegular() || time.Since(info.ModTime()) < 10*time.Second {
			continue
		}
		key := fmt.Sprintf("%d:%d", info.Size(), info.ModTime().UnixNano())
		a.mu.Lock()
		seen := a.seen[e.Name()]
		a.mu.Unlock()
		if seen == key {
			continue
		}
		result, err := a.store.ImportFile(filepath.Join(a.store.Root, "Inbox", e.Name()))
		if err != nil {
			return results, err
		}
		a.mu.Lock()
		a.seen[e.Name()] = key
		a.mu.Unlock()
		results = append(results, result)
	}
	return results, nil
}

func (a *App) pendingInbox() bool {
	list, err := os.ReadDir(filepath.Join(a.store.Root, "Inbox"))
	if err != nil {
		return false
	}
	for _, e := range list {
		if e.IsDir() || strings.HasPrefix(e.Name(), ".") {
			continue
		}
		ext := strings.ToLower(filepath.Ext(e.Name()))
		if ext == ".part" || ext == ".tmp" || ext == ".crdownload" {
			continue
		}
		info, err := e.Info()
		if err != nil || !info.Mode().IsRegular() || time.Since(info.ModTime()) < 10*time.Second {
			continue
		}
		key := fmt.Sprintf("%d:%d", info.Size(), info.ModTime().UnixNano())
		a.mu.Lock()
		seen := a.seen[e.Name()]
		a.mu.Unlock()
		if seen != key {
			return true
		}
	}
	return false
}
func (a *App) runOnce() error {
	a.mu.Lock()
	cfg := a.cfg
	a.mu.Unlock()
	if cfg.WatchEnabled {
		result, err := a.scan()
		if err != nil {
			return err
		}
		a.log("scan", "completed", result)
	}
	if cfg.AutoBackup {
		repo, err := repositoryPath(cfg.Repository, a.store.Vault)
		if err != nil {
			return err
		}
		password, err := rememberedPassword(a.store.Root, repo)
		if err != nil {
			return err
		}
		id, err := a.engine.backup(a.store, repo, password)
		if err != nil {
			return err
		}
		if err = a.updateConfig(func(c *Config) { c.LastBackup = now(); c.LastSnapshot = id }); err != nil {
			return err
		}
		if _, err = a.engine.run(a.store.Root, repo, password, "check"); err != nil {
			return err
		}
		if err = a.updateConfig(func(c *Config) { c.LastCheck = now() }); err != nil {
			return err
		}
		a.log("automatic-backup", "completed", map[string]any{"Snapshot": id})
	}
	return nil
}

func (a *App) backupIfEnabled() error {
	a.mu.Lock()
	enabled := a.cfg.AutoBackup
	a.mu.Unlock()
	if !enabled {
		return nil
	}
	return a.runOnce()
}

// A scheduled invocation delegates to the already running local instance.
// The token is obtained from its local page and is never written to disk.
func forwardRunOnce(root string) error {
	b, err := os.ReadFile(filepath.Join(root, "server-address.txt"))
	if err != nil {
		return err
	}
	address := strings.TrimSpace(string(b))
	u, err := url.Parse(address)
	if err != nil || u.Scheme != "http" || u.Hostname() != "127.0.0.1" || u.Port() == "" {
		return errors.New("некорректный локальный адрес программы")
	}
	client := &http.Client{Timeout: 15 * time.Second}
	response, err := client.Get(address + "/")
	if err != nil {
		return err
	}
	html, err := io.ReadAll(io.LimitReader(response.Body, 2<<20))
	response.Body.Close()
	if err != nil {
		return err
	}
	marker := "const TOKEN='"
	parts := strings.SplitN(string(html), marker, 2)
	if len(parts) != 2 || len(parts[1]) < 49 {
		return errors.New("локальный сеанс не распознан")
	}
	token := parts[1][:48]
	if _, err = hex.DecodeString(token); err != nil {
		return err
	}
	body, _ := json.Marshal(ActionRequest{Action: "run-once"})
	req, err := http.NewRequest("POST", address+"/api/action", bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-BS-Token", token)
	response, err = client.Do(req)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != 200 {
		return errors.New("активная программа занята; операция расписания не принята")
	}
	return nil
}

// User data lives outside the application on Unix so replacing a release or
// moving a macOS app bundle does not replace the archive. --data overrides it.
func defaultDataDir(exe string) (string, error) {
	if runtime.GOOS == "windows" {
		return filepath.Join(filepath.Dir(exe), "Data"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	if runtime.GOOS == "darwin" {
		return filepath.Join(home, "Library", "Application Support", "BerserkerSiDj", "Reserve", "Data"), nil
	}
	base := os.Getenv("XDG_DATA_HOME")
	if !filepath.IsAbs(base) {
		base = filepath.Join(home, ".local", "share")
	}
	return filepath.Join(base, "berserker-sidj", "reserve", "Data"), nil
}

func main() {
	exe, err := os.Executable()
	if err != nil {
		showError(userError(err))
		os.Exit(1)
	}
	defaultRoot, err := defaultDataDir(exe)
	if err != nil {
		showError(userError(err))
		os.Exit(1)
	}
	data := flag.String("data", defaultRoot, "папка рабочих данных")
	once := flag.Bool("run-once", false, "обработать Inbox и создать настроенную резервную копию")
	headless := flag.Bool("no-browser", false, "запустить без открытия браузера")
	listen := flag.String("listen", "127.0.0.1:0", "локальный адрес интерфейса")
	flag.Parse()
	if err = os.MkdirAll(*data, 0700); err != nil {
		showError(userError(err))
		os.Exit(1)
	}
	unlock, err := lockData(*data)
	if err != nil {
		if *once {
			if e := forwardRunOnce(*data); e != nil {
				fmt.Fprintln(os.Stderr, userError(e))
				os.Exit(1)
			}
			return
		}
		if !*once {
			if b, e := os.ReadFile(filepath.Join(*data, "server-address.txt")); e == nil && strings.HasPrefix(string(b), "http://127.0.0.1:") {
				openBrowser(strings.TrimSpace(string(b)))
				return
			}
		}
		showError(userError(err))
		os.Exit(1)
	}
	defer unlock()
	s, err := openStore(*data)
	if err != nil {
		showError(userError(err))
		os.Exit(1)
	}
	binary := filepath.Join(filepath.Dir(exe), "bin", "restic.exe")
	if runtime.GOOS != "windows" {
		binary = filepath.Join(filepath.Dir(exe), "bin", "restic")
	}
	a := &App{store: s, engine: &Engine{Binary: binary, ExpectedHash: ResticHash}, exe: exe, token: randomID(), cfg: loadConfig(s.Root), seen: map[string]string{}}
	if *once {
		if err = a.runOnce(); err != nil {
			a.log("run-once", "error", recordError(err))
			fmt.Fprintln(os.Stderr, userError(err))
			os.Exit(1)
		}
		return
	}
	host, _, err := net.SplitHostPort(*listen)
	if err != nil || host != "127.0.0.1" {
		showError("допустим только адрес 127.0.0.1")
		os.Exit(1)
	}
	ln, err := net.Listen("tcp", *listen)
	if err != nil {
		showError(userError(err))
		os.Exit(1)
	}
	a.baseURL = "http://" + ln.Addr().String()
	srv := &http.Server{Handler: a.handler(), ReadHeaderTimeout: 10 * time.Second, IdleTimeout: 90 * time.Second}
	a.shutdown = func() {
		ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = srv.Shutdown(ctx)
	}
	_ = atomicWrite(filepath.Join(s.Root, "server-address.txt"), []byte(a.baseURL))
	defer os.Remove(filepath.Join(s.Root, "server-address.txt"))
	fmt.Println(a.baseURL)
	if !*headless {
		openBrowser(a.baseURL)
	}
	stop := make(chan struct{})
	defer close(stop)
	go func() {
		ticker := time.NewTicker(20 * time.Second)
		defer ticker.Stop()
		for {
			select {
			case <-stop:
				return
			case <-ticker.C:
				a.mu.Lock()
				enabled := a.cfg.WatchEnabled
				busy := a.job.Running
				a.mu.Unlock()
				if enabled && !busy && a.pendingInbox() {
					_ = a.startJob("watch", func() (any, error) {
						result, err := a.scan()
						if err != nil {
							return result, err
						}
						a.mu.Lock()
						cfg := a.cfg
						a.mu.Unlock()
						changed := false
						if imports, ok := result.([]ImportResult); ok {
							for _, item := range imports {
								if !item.Duplicate {
									changed = true
								}
							}
						}
						if cfg.AutoBackup && changed {
							return result, a.runOnce()
						}
						return result, nil
					})
				}
			}
		}
	}()
	if err = srv.Serve(ln); err != nil && err != http.ErrServerClosed {
		showError(userError(err))
	}
}
