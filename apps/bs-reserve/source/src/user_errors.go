package main

import (
	"archive/zip"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"unicode"
)

// UI messages contain a Russian explanation. The original error is kept only
// in the local diagnostic log; it may contain OS text in any language.
type errorRecord struct {
	Message string
	Details string
}

func recordError(err error) errorRecord {
	return errorRecord{Message: userError(err), Details: err.Error()}
}

// restic's exit codes are stable public protocol, independent of its locale:
// https://restic.readthedocs.io/en/stable/075_scripting.html#exit-codes
// Keep the cause and already password-redacted output for local diagnostics.
type resticError struct {
	Cause  error
	Output string
}

func (e *resticError) Error() string {
	return fmt.Sprintf("restic завершился с ошибкой (%v): %s", e.Cause, e.Output)
}
func (e *resticError) Unwrap() error { return e.Cause }

func driveSuffix(err error) string {
	var p *os.PathError
	if !errors.As(err, &p) {
		return ""
	}
	name := strings.TrimPrefix(p.Path, `\\?\`)
	if len(name) >= 2 && name[1] == ':' && ((name[0] >= 'A' && name[0] <= 'Z') || (name[0] >= 'a' && name[0] <= 'z')) {
		return " " + strings.ToUpper(name[:2])
	}
	return ""
}

func kindMessage(kind string, err error) string {
	switch kind {
	case "disk_full":
		return "Недостаточно свободного места на диске" + driveSuffix(err) + ". Освободите место или перенесите папку данных на другой диск. Операция не завершена."
	case "quota":
		return "Превышен доступный объём хранения. Выберите другой диск или увеличьте лимит места. Операция не завершена."
	case "busy":
		return "Файл занят другой программой. Закройте программу, которая использует файл, и повторите действие."
	case "readonly":
		return "Диск защищён от записи. Снимите защиту или выберите другую папку."
	case "not_ready":
		return "Диск недоступен. Проверьте подключение носителя и выбранный путь."
	case "invalid_path":
		return "Неверное имя файла или папки. Проверьте путь и допустимые символы."
	case "long_path":
		return "Слишком длинное имя файла или путь. Выберите папку с более коротким путём."
	case "io":
		return "Не удалось прочитать или записать данные на диск. Проверьте подключение и состояние носителя."
	}
	return ""
}

func userError(err error) string {
	if err == nil {
		return ""
	}
	if message := kindMessage(systemErrorKind(err), err); message != "" {
		return message
	}
	switch {
	case errors.Is(err, os.ErrPermission):
		return "Нет доступа к файлу или папке. Проверьте права доступа или выберите другую папку."
	case errors.Is(err, os.ErrNotExist):
		return "Файл или папка не найдены. Проверьте путь и подключение носителя."
	case errors.Is(err, os.ErrExist):
		return "Файл или папка с таким именем уже существует. Выберите другое имя или новую пустую папку."
	case errors.Is(err, context.DeadlineExceeded):
		return "Время ожидания операции истекло. Проверьте доступность диска и повторите действие."
	case errors.Is(err, context.Canceled):
		return "Операция отменена."
	case errors.Is(err, zip.ErrChecksum), errors.Is(err, zip.ErrFormat):
		return "ZIP-архив повреждён или имеет неподдерживаемый формат. Проверьте исходный архив или скачайте его заново."
	case errors.Is(err, io.EOF), errors.Is(err, io.ErrUnexpectedEOF):
		return "Получены неполные данные. Повторите действие и проверьте исходный файл."
	}
	var syntax *json.SyntaxError
	var valueType *json.UnmarshalTypeError
	if errors.As(err, &syntax) || errors.As(err, &valueType) {
		return "Не удалось прочитать данные JSON: файл или запрос имеет неверный формат."
	}
	var number *strconv.NumError
	if errors.As(err, &number) {
		return "В запросе указано неверное число. Повторите действие через интерфейс программы."
	}
	var large *http.MaxBytesError
	if errors.As(err, &large) {
		return "Файл или запрос превышает допустимый размер. Выберите меньший файл или отдельные части выгрузки."
	}
	var network net.Error
	if errors.As(err, &network) {
		return "Не удалось связаться с локальной программой. Проверьте, что B/S Reserve запущена, и повторите действие."
	}
	var backup *resticError
	if errors.As(err, &backup) {
		var status interface{ ExitCode() int }
		if errors.As(backup.Cause, &status) {
			switch status.ExitCode() {
			case 3:
				return "Резервная операция завершилась не полностью: часть данных не обработана. Проверьте журнал и повторите операцию после устранения причины."
			case 10:
				return "Резервный репозиторий не найден. Проверьте путь и подключение диска; для новой папки сначала создайте репозиторий."
			case 11:
				return "Резервный репозиторий заблокирован. Дождитесь завершения другой операции. Если блокировка осталась после сбоя, проверьте журнал."
			case 12:
				return "Неверный пароль резервного репозитория. Введите пароль, заданный при его создании."
			}
		}
	}
	// Also translate older saved warnings and the subprocess's textual OS errors.
	text := strings.ToLower(err.Error())
	for _, item := range []struct{ Needle, Kind string }{
		{"there is not enough space on the disk", "disk_full"}, {"no space left on device", "disk_full"},
		{"disk quota exceeded", "quota"}, {"being used by another process", "busy"},
		{"read-only file system", "readonly"}, {"media is write protected", "readonly"},
		{"device is not ready", "not_ready"}, {"file name too long", "long_path"},
		{"input/output error", "io"},
	} {
		if strings.Contains(text, item.Needle) {
			return kindMessage(item.Kind, err)
		}
	}
	if backup != nil {
		return "Движок резервирования не смог завершить операцию. Проверьте журнал: в нём сохранены технические подробности."
	}
	if strings.HasPrefix(err.Error(), "ZIP не прочитан:") || strings.HasPrefix(err.Error(), "JSON больше 256 МиБ") {
		return err.Error()
	}
	if strings.HasPrefix(err.Error(), "разговор не преобразован:") {
		return "Не удалось преобразовать переписку. Проверьте исходный JSON и журнал операций."
	}
	if errors.Unwrap(err) != nil {
		return "Не удалось выполнить операцию. Откройте журнал: там сохранены технические подробности ошибки."
	}
	// Application validation messages are authored in Russian. Unknown external
	// errors get a Russian fallback rather than exposing untranslated OS text.
	for _, r := range strings.TrimSpace(err.Error()) {
		if unicode.In(r, unicode.Cyrillic) {
			return err.Error()
		}
		break
	}
	return "Не удалось выполнить операцию. Откройте журнал: там сохранены технические подробности ошибки."
}

// Read older journal entries without modifying the original diagnostic log.
func logLinesForUI(lines []string) []string {
	result := append([]string(nil), lines...)
	for i, line := range lines {
		var event map[string]any
		if json.Unmarshal([]byte(line), &event) != nil {
			continue
		}
		status, _ := event["Status"].(string)
		raw, ok := event["Result"].(string)
		if ok && (status == "error" || status == "warning") {
			event["Result"] = recordError(errors.New(raw))
			if data, err := json.Marshal(event); err == nil {
				result[i] = string(data)
			}
		}
	}
	return result
}
